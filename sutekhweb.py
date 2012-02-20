# -*- coding: utf-8 -*-
# vim:fileencoding=utf-8 ai ts=4 sts=4 et sw=4
# Copyright 2012 Neil Muller <drnlmuller+sutekh@gmail.com>
# GPL - see COPYING for details

"""The main web-app"""

from flask import Flask, render_template, request, url_for
app = Flask(__name__)

import os
import sys
import urllib

from sqlobject import sqlhub, connectionForURI, SQLObjectNotFound
from sutekh.core.SutekhObjects import AbstractCard, IAbstractCard, \
        IPhysicalCardSet
from sutekh.core.Groupings import MultiTypeGrouping, ClanGrouping, \
        NullGrouping, GroupGrouping, CryptLibraryGrouping, CardTypeGrouping
from sutekh.SutekhUtility import sqlite_uri, prefs_dir
from sutekh.core.CardSetUtilities import find_children, has_children


ALLOWED_GROUPINGS = {
        'No': NullGrouping,
        'Card Type': CardTypeGrouping,
        'Multi Card Type': MultiTypeGrouping,
        'Crypt Group': GroupGrouping,
        'Clan or Creed': ClanGrouping,
        'Crypt or Library': CryptLibraryGrouping
        }


# Utility classes for passing info the jinja2 easily
class CardSetTree(object):
    """object used to build up card set trees for the jinja template"""

    def __init__(self, sName):
        self.name = sName
        self.children = []


class CardCount(object):

    def __init__(self, oCard):
        self.card = oCard
        self.cnt = 0


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
        oTree = CardSetTree(oCS.name)
        aResult.append(oTree)
        if has_children(oCS):
            oTree.children = get_all_children(oCS)
    return aResult


@app.route('/cardsets')
def cardsets():
    """List the collections card sets"""
    aCardSets = get_all_children(None)
    return render_template('cardsets.html', cardsets=aCardSets)


@app.route('/cardsetview/<sCardSetName>')
def cardsetview(sCardSetName):
    try:
        oCS = IPhysicalCardSet(sCardSetName)
    except SQLObjectNotFound:
        oCS = None
    if oCS:
        dCards = {}
        for oCard in oCS.cards:
            dCards.setdefault(oCard.abstractCard, CardCount(oCard.abstractCard))
            dCards[oCard.abstractCard].cnt += 1
        aGrouped = MultiTypeGrouping(dCards.values(), lambda x: x.card)
        return render_template('cardsetview.html', cardset=oCS,
                grouped=aGrouped)
    else:
        return render_template('invalid.html', type='Card Set Name',
                groupings=sorted(ALLOWED_GROUPINGS),
                parent=None)


@app.route('/card/<sCardName>')
def print_card(sCardName):
    """Display card details"""
    sSource = request.args.get('source', None)
    sGrouping = request.args.get('grouping', None)
    sCardSet = request.args.get('cardset', None)
    if sGrouping:
        sParent = url_for(sSource, grouping=sGrouping)
    elif sCardSet:
        sParent = url_for(sSource, sCardSetName=sCardSet)
    else:
        sParent = ''
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
        return render_template('card.html', card=oCard, parent=sParent,
                text=aText)
    else:
        return render_template('invalid_card.html',
                type='Card Name',
                groupings=sorted(ALLOWED_GROUPINGS),
                parent=sParent)


@app.route('/cardlist')
def cardlist():
    """List the WW cardlist"""
    sGroup = request.args.get('grouping', 'Card Type')
    cGrouping = ALLOWED_GROUPINGS.get(sGroup, CardTypeGrouping)
    aGrpData = cGrouping(AbstractCard.select(), IAbstractCard)
    return render_template('cardlist.html', grouped=aGrpData,
            groupings=sorted(ALLOWED_GROUPINGS),
            groupby=sGroup)


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
