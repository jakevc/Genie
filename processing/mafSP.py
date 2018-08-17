import os
import logging
import maf
import pandas as pd
import process_functions
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class mafSP(maf.maf):

	_fileType = "mafSP"

	def _validateFilename(self, filePath):
		assert os.path.basename(filePath[0]) == "nonGENIE_data_mutations_extended_%s.txt" % self.center

	def validate_steps(self, filePathList, **kwargs):
		logger.info("VALIDATING %s" % os.path.basename(filePathList[0]))
		mutationDF = pd.read_csv(filePathList[0],sep="\t",comment="#",na_values = ['-1.#IND', '1.#QNAN', '1.#IND', 
								 '-1.#QNAN', '#N/A N/A', '#N/A', 'N/A', '#NA', 'NULL', 'NaN', 
								 '-NaN', 'nan','-nan',''],keep_default_na=False)
		total_error, warning = self.validate_helper(mutationDF,SP=True)
		return(total_error, warning)

	def storeProcessedMaf(self, filePath, mafSynId, centerMafSynId, isNarrow=False):
		logger.info('STORING %s' % filePath)
		database = self.syn.get(mafSynId)
		#if isNarrow:
		mafDf = pd.read_csv(filePath,sep="\t")
		process_functions.updateData(self.syn, mafSynId, mafDf, self.center, database.primaryKey, toDelete=True)
			#self.syn.store(synapseclient.Table(database.id, filePath, separator="\t"))
		#.syn.store(synapseclient.File(filePath, parentId=centerMafSynId))
		return(filePath)