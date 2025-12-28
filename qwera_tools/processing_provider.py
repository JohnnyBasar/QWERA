# -*- coding: utf-8 -*-
from qgis.core import QgsProcessingProvider
from qgis.PyQt.QtGui import QIcon
import os
from .algorithms.DWD_Stations_Finder import DwdStationFinder
from .algorithms.DWD_Downloader_JustData_v1 import DwdWindDownloader
from .algorithms.DWD_Matrix_Creater_v2 import DwdWindFrequency
from .algorithms.Soil_Erodibility_Mapper import tool_0_3_soil_erodibility
from .algorithms.TOOL_1_LE_Calculator import TOOLBOX_1
from .algorithms.TOOL_2_Windshade_Calculator import TOOLBOX_2_HILLSHADES
from .algorithms.ADF_to_Tif import ADF2TIFF_Batch
from .algorithms.TOOL_3_Wind_Protection_Mapper import wind_protection_classes
from .algorithms.Tool_4_Soil_Susceptibility_Mapper import tool_4_susceptibility_of_soils_to_wind_erosion
from .algorithms.Tool_5_Riskshare_Mapper import TOOLBOX_5_FeldbloeckeRiskShare
from .algorithms.Wind_Statistics import WIND_STATS
from .algorithms.WindFrequencyFromTable import WindFrequencyFromTable


def _provider_icon():
    plugin_dir = os.path.dirname(__file__)
    return QIcon(os.path.join(plugin_dir, "icons", "icon.svg"))

class QWeraProcessingProvider(QgsProcessingProvider):
    def loadAlgorithms(self):
        self.addAlgorithm(DwdStationFinder())
        self.addAlgorithm(DwdWindDownloader())
        self.addAlgorithm(DwdWindFrequency())
        self.addAlgorithm(tool_0_3_soil_erodibility())
        self.addAlgorithm(TOOLBOX_1())
        self.addAlgorithm(TOOLBOX_2_HILLSHADES())
        self.addAlgorithm(ADF2TIFF_Batch())
        self.addAlgorithm(wind_protection_classes())
        self.addAlgorithm(tool_4_susceptibility_of_soils_to_wind_erosion())
        self.addAlgorithm(TOOLBOX_5_FeldbloeckeRiskShare())
        self.addAlgorithm(WIND_STATS())
        self.addAlgorithm(WindFrequencyFromTable())

    def id(self):
        return "qwera_tools"

    def name(self):
        return "QWERA Tools"
    
    def icon(self):
        # Pfad relativ zu diesem Dateiordner
        return _provider_icon()
