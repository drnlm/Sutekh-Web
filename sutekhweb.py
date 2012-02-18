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


@app.route('/')
def start():
    return render_template('index.html', groupings=sorted(ALLOWED_GROUPINGS))


class CardSetTree(object):
    """object used to build up card set trees for the jinja template"""

    def __init__(self, name):
        self.name = name
        self.children = []


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


@app.route('/cardsetview')
def cardsetview():
    sCardSetName = request.args.get('name', 'No Card')
    try:
        oCS = IPhysicalCardSet(sCardSetName)
    except SQLObjectNotFound:
        # We try this, as &'s in the name confuse flask
        # XXX: There must be a better way to do this
        _, sData = request.url.split('?name=')
        sCardSetName = urllib.unquote(sData)
        print sData, sCardSetName
        try:
            oCS = IPhysicalCardSet(sCardSetName)
        except SQLObjectNotFound:
            oCS = None
    if oCS:
        dCards = {}
        for oCard in oCS.cards:
            dCards.setdefault(oCard.abstractCard, 0)
            dCards[oCard.abstractCard] += 1
        aGrouped = MultiTypeGrouping(dCards.items(), lambda x: x[0])
        return render_template('cardsetview.html', cardset=oCS,
                grouped=aGrouped)
    else:
        return render_template('invalid.html', type='Card Set Name',
                groupings=sorted(ALLOWED_GROUPINGS),
                parent=None)


@app.route('/card')
def print_card():
    """Display card details"""
    sCardName = request.args.get('name', 'No Card')
    sSource = request.args.get('source', None)
    sGrouping = request.args.get('grouping', None)
    sCardSet = request.args.get('cardset', None)
    if sGrouping:
        sParent = url_for(sSource, grouping=sGrouping)
    elif sCardSet:
        sParent = url_for(sSource, name=sCardSet)
    else:
        sParent = ''
    try:
        oCard = IAbstractCard(sCardName)
    except SQLObjectNotFound:
        oCard = None
    if oCard:
        return render_template('card.html', card=oCard, parent=sParent)
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


# FIXME: Add proper argument passing

if __name__ == "__main__":
    sPrefsDir = prefs_dir("Sutekh")
    sUri = sqlite_uri(os.path.join(sPrefsDir, "sutekh.db"))
    oConn = connectionForURI(sUri)
    sqlhub.processConnection = oConn
    bDebug = False
    try:
        if sys.argv[1] == '--debug':
            bDebug = True
    except IndexError:
        bDebug = False
    if bDebug:
        app.run(debug=True)
    else:
        app.run(host='0.0.0.0')
