Sutekh-Web
==========

Description
-----------

This is a simple flask based web-interface to the sutekh card database

It currently allows:

* Displaying the WW card list
* Display the details of a card
* Browsing your collection of card sets
* Browsing a card set


Current requirments:
-------------------

Flask 0.8
Jinja2 2.6

Configuration:
--------------

You can specify a config file to load by setting the `SUTEKH_WEB_CONFIG`
enviroment variable to point to the correct file.

Supporting icons:
-----------------

To display icons, copy the icons downloaded by sutekh into /static/icons
(maintaining the directory structure, so clans in /static/icons/clans and so
forth) and set 'ICONS = True' in the config file

Jquery Tree support
-------------------

Sutekh-Web includes jquery and jquery.treeTable under static/jquery to simplify
deployment - these can be replaced if required.

This includes jquery 3.5.1 and jquery.treeTable 3.2.0-1, downloaded via npm in
November 2020.
