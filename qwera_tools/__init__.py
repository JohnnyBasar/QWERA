# -*- coding: utf-8 -*-
def classFactory(iface):
    from .plugin import QWeraToolsPlugin
    return QWeraToolsPlugin(iface)
