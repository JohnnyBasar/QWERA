# -*- coding: utf-8 -*-

import os, sys


from qgis.core import QgsApplication
from .processing_provider import QWeraProcessingProvider
#from qgis.PyQt.QtGui import QIcon
#import os

class QWeraToolsPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.provider = None

    def initGui(self):
        self.provider = QWeraProcessingProvider()
        QgsApplication.processingRegistry().addProvider(self.provider)

    def unload(self):
        if self.provider:
            QgsApplication.processingRegistry().removeProvider(self.provider)
            self.provider = None
            
    
