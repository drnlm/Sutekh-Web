# -*- coding: utf-8 -*-
# vim:fileencoding=utf-8 ai ts=4 sts=4 et sw=4
# Copyright 2012 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - see COPYING for details

"""The main web-app"""

from flask import (Flask, render_template, request, url_for, redirect,
                   send_file)
app = Flask(__name__)

import os
from urllib.parse import quote, unquote
from io import StringIO, BytesIO

from sqlobject import sqlhub, connectionForURI, SQLObjectNotFound

from sutekh.base.core.BaseTables import (AbstractCard,
                                         MapPhysicalCardToPhysicalCardSet)
from sutekh.base.core.BaseAdapters import (IAbstractCard, IPhysicalCardSet,
                                           IKeyword, IPhysicalCard,
                                           IPrintingName)
from sutekh.base.core.FilterParser import FilterParser, escape
from sutekh.base.core.CardSetHolder import CardSetWrapper
from sutekh.base.core.CardSetUtilities import find_children, has_children
from sutekh.base.core.BaseFilters import (NullFilter, MultiCardTypeFilter,
                                          MultiKeywordFilter,
                                          PhysicalCardSetFilter, FilterAndBox)
from sutekh.base.core.BaseGroupings import (MultiTypeGrouping,
                                            NullGrouping,
                                            CardTypeGrouping)
from sutekh.base.core.DBUtility import init_cache
from sutekh.base.Utility import sqlite_uri, prefs_dir, safe_filename

from sutekh.core.Filters import (MultiClanFilter, MultiVirtueFilter,
                                 MultiCreedFilter,
                                 MultiDisciplineFilter)
from sutekh.core.Groupings import (ClanGrouping, GroupGrouping,
                                   CryptLibraryGrouping)
from sutekh.SutekhUtility import is_crypt_card
from sutekh.io.IconManager import IconManager
from sutekh.io.PhysicalCardSetWriter import PhysicalCardSetWriter


ALLOWED_GROUPINGS = {'No': NullGrouping,
                     'Card Type': CardTypeGrouping,
                     'Multi Card Type': MultiTypeGrouping,
                     'Crypt Group': GroupGrouping,
                     'Clan or Creed': ClanGrouping,
                     'Crypt or Library': CryptLibraryGrouping
                     }

STRING_FILTERS = [('cardname', 'CardName'),
                  ('cardtext', 'CardText'),
                  ]

LIST_FILTERS = [('cardtype', 'CardType', MultiCardTypeFilter),
                ('discipline', 'Discipline', MultiDisciplineFilter),
                ('virtue', 'Virtue', MultiVirtueFilter),
                ('clan', 'Clan', MultiClanFilter),
                ('creed', 'Creed', MultiCreedFilter),
                ('keyword', 'Keyword', MultiKeywordFilter),
                ]


# Utility classes and functions for passing info the jinja2 easily
def double_quote(sString):
    """Double quote a string with urllib.parse.quote, including / as a quoted
       character.

       Needed to bypass flask's unquoting in some cases."""
    return quote(quote(sString, safe=''))


class CardSetTree(object):
    """object used to build up card set trees for the jinja template"""

    __slots__ = ["name", "inuse", "linkname", "children", "info", "nodeid",
                 "parent"]

    def __init__(self, sName, bInUse, oParent, iId):
        self.name = sName
        self.inuse = bInUse
        self.linkname = double_quote(sName.encode('utf8'))
        self.parent = ''
        self.nodeid = 'node%d' % iId
        if oParent:
            self.parent = oParent.nodeid
        self.children = []
        self.info = ''


class PrintingCount(object):
    """Helper object from counting expansion info"""

    __slots__ = ['print_name', 'cnt']

    def __init__(self, oPrinting):
        if oPrinting:
            self.print_name = IPrintingName(oPrinting)
        else:
            self.print_name = ' Unknown Expansion'
        self.cnt = 0


class CardCount(object):
    """Helper object for counting cards in a card set"""

    __slots__ = ['card', 'cnt', 'printings']

    def __init__(self, oCard):
        self.card = oCard
        self.cnt = 0
        self.printings = {}


class WebIconManager(IconManager):
    """Handle icons for the web app"""

    def _get_icon(self, sFileName, _iSize=12):
        """Return the correct url for the icon"""
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
        dNewIcons = {}
        for sName, oIcon in dIcons.items():
            # Filter out any icons for which there is no filename
            if oIcon:
                dNewIcons[sName] = oIcon
        return dNewIcons


# Icon Manager is global, so we don't have to keep creating it
# icon path isn't currently configurable, although it should be
ICON_MANAGER = WebIconManager('icons')
# Likewise for the Filter Parser
PARSER = FilterParser()


# default config
class DefConfig(object):
    """Default config for the web app"""
    DEBUG = False
    LISTEN = '0.0.0.0'
    SUTEKH_PREFS = prefs_dir("Sutekh")
    DATABASE_URI = sqlite_uri(os.path.join(SUTEKH_PREFS, "sutekh.db"))
    ICONS = False


@app.route('/')
def start():
    """Entry point for the flask web app"""
    return render_template('index.html', groupings=sorted(ALLOWED_GROUPINGS))


def get_all_children(oParent, iId, oParNode=None):
    """Get all the child card sets of the given parent card set and add
       then to a CardSetTree"""
    aResult = []
    for oCS in sorted(find_children(oParent), key=lambda x: x.name):
        iId += 1
        oTree = CardSetTree(oCS.name, oCS.inuse, oParNode, iId)
        aResult.append(oTree)
        if has_children(oCS):
            oTree.children, iId = get_all_children(oCS, iId, oTree)
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
    return aResult, iId


@app.route('/cardsets')
def cardsets():
    """List the collections card sets"""
    aCardSets, _ = get_all_children(None, 0)
    return render_template('cardsets.html', cardsets=aCardSets)


@app.route('/cardsetview/<sCardSetName>', methods=['GET', 'POST'])
@app.route('/cardsetview/<sCardSetName>/<sGrouping>', methods=['GET', 'POST'])
@app.route('/cardsetview/<sCardSetName>/<sGrouping>/<sExpMode>',
           methods=['GET', 'POST'])
def cardsetview(sCardSetName, sGrouping=None, sExpMode='Hide'):
    """Show the card set with the given name and parameters"""
    sCorrectName = unquote(sCardSetName)
    try:
        oCS = IPhysicalCardSet(sCorrectName)
    except SQLObjectNotFound:
        oCS = None
    if request.method == 'POST':
        # Form submission
        if 'grouping' in request.form:
            sFilter = request.values.get('curfilter', '')
            sExpMode = request.values.get('showexp', 'Hide')
            return redirect(url_for('change_grouping', source='cardsetview',
                                    cardsetname=sCardSetName,
                                    showexp=sExpMode,
                                    curfilter=sFilter))
        elif 'filter' in request.form:
            sGrouping = request.values.get('curgrouping', 'Card Type')
            sExpMode = request.values.get('showexp', 'Hide')
            return redirect(url_for('filter', source='cardsetview',
                                    cardsetname=sCardSetName,
                                    showexp=sExpMode,
                                    grouping=sGrouping))
        elif 'download' in request.form:
            if oCS:
                oWriter = PhysicalCardSetWriter()
                oXMLFile = StringIO()
                oWriter.write(oXMLFile, CardSetWrapper(oCS))
                oXMLFile.seek(0)  # reset to start
                # Convert to bytes for flask
                oOutput = BytesIO(oXMLFile.getvalue().encode('utf8'))
                oOutput.seek(0)
                return send_file(oOutput,
                                 mimetype="application/octet-stream",
                                 as_attachment=True,
                                 attachment_filename=safe_filename(
                                     "%s.xml" % sCorrectName))
            else:
                return render_template('invalid.html', type='Card Set Name',
                                       requested=sCardSetName)
        elif 'expansions' in request.form:
            sFilter = request.values.get('curfilter', '')
            sGrouping = request.values.get('curgrouping', 'Card Type')
            if request.values['expansions'] == 'Hide Expansions':
                return redirect(url_for('cardsetview',
                                        sCardSetName=sCardSetName,
                                        sGrouping=sGrouping,
                                        sExpMode='Hide', filter=sFilter))
            else:
                return redirect(url_for('cardsetview',
                                        sCardSetName=sCardSetName,
                                        sGrouping=sGrouping,
                                        sExpMode='Show', filter=sFilter))
    elif request.method == 'GET':
        if oCS:
            dCards = {}
            dCounts = {'crypt': 0, 'library': 0}
            cGrouping = ALLOWED_GROUPINGS.get(sGrouping, CardTypeGrouping)
            sFilter = request.args.get('filter', None)
            if sFilter and sFilter != 'None':
                try:
                    oCardFilter = PARSER.apply(sFilter).get_filter()
                    oCSFilter = PhysicalCardSetFilter(oCS.name)
                    oFilter = FilterAndBox([oCSFilter, oCardFilter])
                    aResults = oFilter.select(MapPhysicalCardToPhysicalCardSet)
                    aCards = [IPhysicalCard(x) for x in aResults]
                except Exception:
                    aCards = oCS.cards
            else:
                aCards = oCS.cards
            for oCard in aCards:
                iCardCount = CardCount(oCard.abstractCard)
                oCount = dCards.setdefault(oCard.abstractCard, iCardCount)
                oCount.cnt += 1
                iPrintingCount = PrintingCount(oCard.printing)
                oPrintingCount = oCount.printings.setdefault(oCard.printing,
                                                         iPrintingCount)
                oPrintingCount.cnt += 1
                if is_crypt_card(oCard.abstractCard):
                    dCounts['crypt'] += 1
                else:
                    dCounts['library'] += 1
            aGrouped = cGrouping(dCards.values(), lambda x: x.card)
            bShowExpansions = (sExpMode == 'Show')
            if not sGrouping:
                sGrouping = 'Card Type'
            return render_template('cardsetview.html', cardset=oCS,
                                   grouped=aGrouped, counts=dCounts,
                                   quotedname=quote(oCS.name, safe=''),
                                   curfilter=sFilter,
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
            sText = oCard.text.replace(
                '{', '<span class="errata">').replace('}', '</span>')
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
        sFilter = request.args.get('curfilter', '')
        return render_template('grouping.html',
                               groupings=sorted(ALLOWED_GROUPINGS),
                               source=sSource, cardsetname=sCardSet,
                               showexp=sExpMode, curfilter=sFilter)
    elif request.method == 'POST':
        sNewGrouping = request.form['grouping']
        sFilter = request.form['curfilter']
        sSource = request.form['source']
        if sSource == 'cardlist':
            if sFilter and sFilter != 'None':
                return redirect(url_for(sSource, sGrouping=sNewGrouping,
                                        filter=sFilter))
            return redirect(url_for(sSource, sGrouping=sNewGrouping))
        else:
            sCardSet = request.form['cardset']
            sExpMode = request.form['showexp']
            if sFilter and sFilter != 'None':
                return redirect(url_for(sSource, sCardSetName=sCardSet,
                                        sGrouping=sNewGrouping,
                                        sExpMode=sExpMode, filter=sFilter))
            return redirect(url_for(sSource, sCardSetName=sCardSet,
                                    sGrouping=sNewGrouping,
                                    sExpMode=sExpMode))
    else:
        print('Error, fell off the back of the world')


@app.route('/cardlist', methods=['GET', 'POST'])
@app.route('/cardlist/<sGrouping>', methods=['GET', 'POST'])
def cardlist(sGrouping=None):
    """List the WW cardlist"""
    if request.method == 'POST':
        # Form submission
        if 'grouping' in request.form:
            sFilter = request.values.get('curfilter', '')
            return redirect(url_for('change_grouping', source='cardlist',
                                    curfilter=sFilter))
        elif 'filter' in request.form:
            sGroup = request.values.get('curgrouping', 'Card Type')
            return redirect(url_for('filter', source='cardlist',
                                    grouping=sGroup))
    if sGrouping is None:
        sGroup = 'Card Type'
    else:
        sGroup = sGrouping
    sFilter = request.args.get('filter', None)
    if sFilter and sFilter != 'None':
        try:
            oFilter = PARSER.apply(sFilter).get_filter()
        except Exception:
            oFilter = NullFilter()
    else:
        oFilter = NullFilter()
    dCounts = {'crypt': 0, 'library': 0}
    cGrouping = ALLOWED_GROUPINGS.get(sGrouping, CardTypeGrouping)
    for oCard in oFilter.select(AbstractCard):
        if is_crypt_card(oCard):
            dCounts['crypt'] += 1
        else:
            dCounts['library'] += 1
    aGrpData = cGrouping(oFilter.select(AbstractCard), IAbstractCard)
    return render_template('cardlist.html', grouped=aGrpData,
                           groupings=sorted(ALLOWED_GROUPINGS),
                           counts=dCounts, grouping=sGroup,
                           curfilter=sFilter)


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


@app.route('/filter', methods=['GET', 'POST'])
def filter():
    """Support some of the Sutekh Filter Options"""
    if request.method == 'POST':
        sCurGrouping = request.form['grouping']
        sSource = request.form['source']
        sCardSet = request.form['cardset']
        sExpMode = request.form['showexp']
        sComb = ' %s ' % request.form['combine']
        aFilterBits = []
        for sElement, sFilter in STRING_FILTERS:
            if sElement in request.form:
                sData = request.form[sElement]
                if sData:
                    aFilterBits.append('%s = "%s"' % (sFilter, escape(sData)))
        for sElement, sFilter, _ in LIST_FILTERS:
            if sElement in request.form:
                sValues = ','.join(['"%s"' % x for x in
                                    request.form.getlist(sElement)])
                aFilterBits.append('%s = %s' % (sFilter, sValues))
        sTotalFilter = sComb.join(aFilterBits)
        if sSource == 'cardlist':
            return redirect(url_for(sSource, sGrouping=sCurGrouping,
                                    filter=sTotalFilter))
        return redirect(url_for(sSource, sCardSetName=sCardSet,
                                sGrouping=sCurGrouping, sExpMode=sExpMode,
                                filter=sTotalFilter))
    else:
        sSource = request.args.get('source', 'cardlist')
        sCardSet = request.args.get('cardsetname', '')
        sExpMode = request.args.get('showexp', 'Hide')
        sGroupBy = request.args.get('grouping', 'Card Type')
        aListFilters = []
        for sElement, sText, cCls in LIST_FILTERS:
            aListFilters.append((sElement, sText, cCls.get_values()))
        return render_template('filter.html', grouping=sGroupBy,
                               source=sSource, cardsetname=sCardSet,
                               showexp=sExpMode,
                               listfilters=aListFilters,
                               stringfilters=STRING_FILTERS)


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
    # Initialise database caches
    init_cache()
    if bDebug:
        app.run()
    else:
        app.run(host=app.config['LISTEN'])
