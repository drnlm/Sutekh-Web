# -*- coding: utf-8 -*-
# vim:fileencoding=utf-8 ai ts=4 sts=4 et sw=4
# Copyright 2012 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - see COPYING for details

"""The main web-app"""

from flask import Flask, render_template, request, url_for, redirect
app = Flask(__name__)

import os
import urllib

from sqlobject import sqlhub, connectionForURI, SQLObjectNotFound
from sutekh.core.SutekhObjects import AbstractCard, IAbstractCard, \
        IPhysicalCardSet, IKeyword
from sutekh.core.FilterParser import FilterParser
from sutekh.core.Filters import NullFilter
from sutekh.core.Groupings import MultiTypeGrouping, ClanGrouping, \
        NullGrouping, GroupGrouping, CryptLibraryGrouping, CardTypeGrouping
from sutekh.SutekhUtility import sqlite_uri, prefs_dir, is_crypt_card
from sutekh.core.CardSetUtilities import find_children, has_children
from sutekh.io.IconManager import IconManager


ALLOWED_GROUPINGS = {
        'No': NullGrouping,
        'Card Type': CardTypeGrouping,
        'Multi Card Type': MultiTypeGrouping,
        'Crypt Group': GroupGrouping,
        'Clan or Creed': ClanGrouping,
        'Crypt or Library': CryptLibraryGrouping
        }


# Utility classes and functions for passing info the jinja2 easily
def double_quote(sString):
    """Double quote a string with urllib.quote, including / as a quoted
       character.

       Needed to bypass flask's unquoting in some cases."""
    return urllib.quote(urllib.quote(sString, safe=''))


class CardSetTree(object):
    """object used to build up card set trees for the jinja template"""

    __slots__ = ["name", "inuse", "linkname", "children", "info"]

    def __init__(self, sName, bInUse):
        self.name = sName
        self.inuse = bInUse
        self.linkname = double_quote(sName)
        self.children = []
        self.info = ''


class ExpCount(object):
    """Helper object from counting expansion info"""

    __slots__ = ['expname', 'cnt']

    def __init__(self, oExp):
        if oExp:
            self.expname = oExp.name
        else:
            self.expname = ' Unknown Expansion'
        self.cnt = 0


class CardCount(object):
    """Helper object for counting cards in a card set"""

    __slots__ = ['card', 'cnt', 'expansions']

    def __init__(self, oCard):
        self.card = oCard
        self.cnt = 0
        self.expansions = {}


class WebIconManager(IconManager):

    def _get_icon(self, sFileName, _iSize=12):
        if sFileName:
            return url_for('static',
                    filename='/'.join((self._sPrefsDir, sFileName)))
        return None

    def get_all_icons(self, oCard):
        """Returns a dictionarty of all the icons appropriate for
           the given card"""
        dIcons = {}
        if oCard.cardtype:
            dIcons.update(self._get_card_type_icons(oCard.cardtype))
        if oCard.creed:
            dIcons.update(self._get_creed_icons(oCard.creed))
        if oCard.clan:
            dIcons.update(self._get_clan_icons(oCard.clan))
        if oCard.discipline:
            dIcons.update(self._get_discipline_icons(oCard.discipline))
        if oCard.virtue:
            dIcons.update(self._get_virtue_icons(oCard.virtue))
        if oCard.virtue:
            dIcons.update(self._get_virtue_icons(oCard.virtue))
        for oItem in oCard.keywords:
            if oItem == IKeyword('burn option'):
                dIcons.update({oItem.keyword:
                    self.get_icon_by_name('burn option')})
            elif oItem == IKeyword('advanced'):
                dIcons.update({oItem.keyword:
                    self.get_icon_by_name('advanced')})
        return dIcons


# Icon Manager is global, so we don't have to keep creating it
# icon path isn't currently configurable, although it should be
ICON_MANAGER = WebIconManager('icons')
# Likewise for the Filter Parser
PARSER = FilterParser()


# default config
class DefConfig(object):
    DEBUG = False
    LISTEN = '0.0.0.0'
    SUTEKH_PREFS = prefs_dir("Sutekh")
    DATABASE_URI = sqlite_uri(os.path.join(SUTEKH_PREFS, "sutekh.db"))
    ICONS = False


@app.route('/')
def start():
    return render_template('index.html', groupings=sorted(ALLOWED_GROUPINGS))


def get_all_children(oParent):
    aResult = []
    for oCS in sorted(find_children(oParent), key=lambda x: x.name):
        oTree = CardSetTree(oCS.name, oCS.inuse)
        aResult.append(oTree)
        if has_children(oCS):
            oTree.children = get_all_children(oCS)
            if oTree.children:
                iNumInUse = len([x for x in oTree.children if x.inuse])
                if len(oTree.children) == 1:
                    sChild = 'child'
                else:
                    sChild = 'children'
                if iNumInUse:
                    oTree.info = ' (%d %s, %d marked in use)' % (
                            len(oTree.children), sChild, iNumInUse)
                else:
                    oTree.info = ' (%d %s)' % (len(oTree.children), sChild)
    return aResult


@app.route('/cardsets')
def cardsets():
    """List the collections card sets"""
    aCardSets = get_all_children(None)
    return render_template('cardsets.html', cardsets=aCardSets)


@app.route('/cardsetview/<sCardSetName>', methods=['GET', 'POST'])
@app.route('/cardsetview/<sCardSetName>/<sGrouping>', methods=['GET', 'POST'])
@app.route('/cardsetview/<sCardSetName>/<sGrouping>/<sExpMode>',
        methods=['GET', 'POST'])
def cardsetview(sCardSetName, sGrouping=None, sExpMode='Hide'):
    if request.method == 'POST':
        # Form submission
        if 'grouping' in request.form:
            sExpMode = request.values.get('showexp', 'Hide')
            return redirect(url_for('change_grouping', source='cardsetview',
                cardsetname=sCardSetName, showexp=sExpMode))
        elif 'filter' in request.form:
            sExpMode = request.args.get('showexp', 'Hide')
            return redirect(url_for('filter', source='cardsetview',
                cardsetname=sCardSetName, showexp=sExpMode))
        elif 'expansions' in request.form:
            sGrouping = request.values.get('curgrouping', 'Card Type')
            if request.values['expansions'] == 'Hide Expansions':
                return redirect(url_for('cardsetview',
                    sCardSetName=sCardSetName, sGrouping=sGrouping,
                    sExpMode='Hide'))
            else:
                return redirect(url_for('cardsetview',
                    sCardSetName=sCardSetName, sGrouping=sGrouping,
                    sExpMode='Show'))
    elif request.method == 'GET':
        sCorrectName = urllib.unquote(sCardSetName)
        try:
            oCS = IPhysicalCardSet(sCorrectName)
        except SQLObjectNotFound:
            oCS = None
        if oCS:
            dCards = {}
            dCounts = {'crypt': 0, 'library': 0}
            for oCard in oCS.cards:
                oCount = dCards.setdefault(oCard.abstractCard,
                        CardCount(oCard.abstractCard))
                oCount.cnt += 1
                oExpCount = oCount.expansions.setdefault(oCard.expansion,
                        ExpCount(oCard.expansion))
                oExpCount.cnt += 1
                if is_crypt_card(oCard.abstractCard):
                    dCounts['crypt'] += 1
                else:
                    dCounts['library'] += 1
            cGrouping = ALLOWED_GROUPINGS.get(sGrouping, CardTypeGrouping)
            aGrouped = cGrouping(dCards.values(), lambda x: x.card)
            bShowExpansions = sExpMode == 'Show'
            if not sGrouping:
                sGrouping = 'Card Type'
            return render_template('cardsetview.html', cardset=oCS,
                    grouped=aGrouped, counts=dCounts,
                    quotedname=urllib.quote(oCS.name, safe=''),
                    grouping=sGrouping,
                    showexpansions=bShowExpansions)
        else:
            return render_template('invalid.html', type='Card Set Name',
                    requested=sCardSetName)


@app.route('/card/<sCardName>')
def print_card(sCardName):
    """Display card details"""
    try:
        oCard = IAbstractCard(sCardName)
    except SQLObjectNotFound:
        oCard = None
    if oCard:
        if oCard.text:
            # Mark errata clearly
            sText = oCard.text.replace('{',
                    '<span class="errata">').replace('}', '</span>')
            # We split text into lines, so they can be neatly
            # formatted by the template
            # FIXME: This is messy - should we preserve more formatting
            # in the database?
            aText = sText.split("\n")
            if '. [' in aText[-1]:
                # Split discipline level text
                aSplit = aText.pop().split('. [')
                # Fix the lines
                aText.append(aSplit[0] + '.')
                for sLine in aSplit[1:-1]:
                    aText.append('[' + sLine + '.')
                aText.append('[' + aSplit[-1])
        else:
            aText = []
        if app.config['ICONS']:
            # Extract icons
            dIcons = ICON_MANAGER.get_all_icons(oCard)
        else:
            dIcons = {}
        if oCard.rarity:
            dExp = {}
            for oPair in oCard.rarity:
                dExp.setdefault(oPair.expansion.name, [])
                dExp[oPair.expansion.name].append(oPair.rarity.name)
            # Create the sorted display list
            aExpansions = [(x, ", ".join(sorted(dExp[x])))
                    for x in sorted(dExp)]
        else:
            aExpansions = []
        if oCard.rulings:
            aRulings = [(oR.text.replace("\n", " "), oR.code, oR.url)
                    for oR in oCard.rulings]
        else:
            aRulings = []
        return render_template('card.html', card=oCard, text=aText,
                icons=dIcons, expansions=aExpansions,
                rulings=aRulings)
    else:
        return render_template('invalid.html', type='Card Name',
                requested=sCardName)


@app.route('/grouping', methods=['GET', 'POST'])
def change_grouping():
    """Handle changing the grouping"""
    if request.method == 'GET':
        sSource = request.args.get('source', 'cardlist')
        sCardSet = request.args.get('cardsetname', '')
        sExpMode = request.args.get('showexp', 'Hide')
        return render_template('grouping.html',
                groupings=sorted(ALLOWED_GROUPINGS), source=sSource,
                cardsetname=sCardSet, showexp=sExpMode)
    elif request.method == 'POST':
        sNewGrouping = request.form['grouping']
        sSource = request.form['source']
        if sSource == 'cardlist':
            return redirect(url_for(sSource, sGrouping=sNewGrouping))
        else:
            sCardSet = request.form['cardset']
            sExpMode = request.form['showexp']
            return redirect(url_for(sSource, sCardSetName=sCardSet,
                sGrouping=sNewGrouping, sExpMode=sExpMode))
    else:
        print 'Error, fell off the back of the world'


@app.route('/cardlist', methods=['GET', 'POST'])
@app.route('/cardlist/<sGrouping>', methods=['GET', 'POST'])
def cardlist(sGrouping=None):
    """List the WW cardlist"""
    if request.method == 'POST':
        # Form submission
        if 'grouping' in request.form:
            return redirect(url_for('change_grouping', source='cardlist'))
        elif 'filter' in request.form:
            return redirect(url_for('filter', source='cardlist'))
    if sGrouping is None:
        sGroup = 'Card Type'
    else:
        sGroup = sGrouping
    sFilter = request. args.get('filter', None)
    if sFilter:
        oFilter = PARSER.apply(sFilter).get_filter()
    else:
        oFilter = NullFilter()
    cGrouping = ALLOWED_GROUPINGS.get(sGrouping, CardTypeGrouping)
    aGrpData = cGrouping(oFilter.select(AbstractCard), IAbstractCard)
    return render_template('cardlist.html', grouped=aGrpData,
            groupings=sorted(ALLOWED_GROUPINGS),
            groupby=sGroup)


@app.route('/search', methods=['GET', 'POST'])
@app.route('/search/<sType>', methods=['GET', 'POST'])
def simple_search(sType='Card Name'):
    """Allow searching on Card Name"""
    if request.method == 'POST':
        if 'searchtext' in request.form:
            if sType == "Card Name":
                sFilter = 'CardName = "%s"' % request.form['searchtext']
            elif sType == "Card Text":
                sFilter = 'CardText = "%s"' % request.form['searchtext']
            else:
                return render_template('invalid.html', type='Search Type',
                        requested=sType)
            return redirect(url_for('cardlist', filter=sFilter))
        else:
            return redirect(url_for('cardlist'))
    else:
        if sType in ['Card Name', 'Card Text']:
            return render_template('simple_search.html', type=sType)
        return render_template('invalid.html', type='Search Type',
                requested=sType)


@app.route('/filter')
def filter():
    return render_template('filter.html')


if __name__ == "__main__":
    app.config.from_object(DefConfig)
    try:
        app.config.from_envvar('SUTEKH_WEB_CONFIG')
    except RuntimeError:
        # We don't require the env be set, so ignore
        # this runtime error
        pass
    oConn = connectionForURI(app.config['DATABASE_URI'])
    sqlhub.processConnection = oConn
    bDebug = app.config['DEBUG']
    if bDebug:
        app.run()
    else:
        app.run(host=app.config['LISTEN'])
