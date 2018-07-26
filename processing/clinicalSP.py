import process_functions
import os
import logging
import pandas as pd
import example_filetype_format
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class clinicalSP(example_filetype_format.FileTypeFormat):
    
    _fileType = "clinicalSP"

    # VALIDATE FILENAME
    def _validateFilename(self, filePath):
    	assert os.path.basename(filePath[0]) == "nonGENIE_data_clinical.txt"

    def process_steps(self, filePath, **kwargs):
    	logger.info('PROCESSING %s' % filePath)
        newPath = kwargs['newPath']
        databaseSynId = kwargs['databaseSynId']
    	clinicalSPDf = pd.read_csv(filePath, sep="\t", comment="#")
    	clinicalSPDf['SAMPLE_ID'] = [process_functions.checkGenieId(sample, self.center) for sample in clinicalSPDf['SAMPLE_ID']]
    	clinicalSPDf['CENTER'] = self.center
    	clinicalSPDf['PATIENT_ID'] = [process_functions.checkGenieId(sample, self.center) for sample in clinicalSPDf['PATIENT_ID']]
    	cols = clinicalSPDf.columns
    	process_functions.updateData(self.syn, databaseSynId, clinicalSPDf, self.center, cols)
    	clinicalSPDf.to_csv(newPath, sep="\t",index=False)
    	return(newPath)

    # VALIDATION
    def validate_steps(self, filePathList, **kwargs):
        """
        This function validates the clinical file to make sure it adhere to the clinical SOP.
        
        :params clinicalFilePath:              Flattened clinical file or patient clinical file
        :params clinicalSamplePath:            Sample clinical file if patient clinical file is provided

        :returns:                              Error message
        """
        filePath = filePathList[0]
        logger.info("VALIDATING %s" % os.path.basename(filePath))
        clinicalDF = pd.read_csv(filePath,sep="\t",comment="#")
        clinicalDF.columns = [col.upper() for col in clinicalDF.columns]
        clinicalDF = clinicalDF.fillna("")
        total_error = ""
        warning = ""

        #CHECK: SAMPLE_ID
        haveColumn = process_functions.checkColExist(clinicalDF, 'SAMPLE_ID')
        if not haveColumn:
            total_error += "nonGENIE_data_clinical.txt: File must have SAMPLE_ID column.\n"
        else:
            if sum(clinicalDF['SAMPLE_ID'].isnull()) > 0:
                total_error += "nonGENIE_data_clinical.txt: There can't be any blank values for SAMPLE_ID\n"

        #CHECK: SEQ_ASSAY_ID
        haveColumn = process_functions.checkColExist(clinicalDF, "SEQ_ASSAY_ID")
        if haveColumn:
            if not all([i != "" for i in clinicalDF['SEQ_ASSAY_ID']]):
                warning += "nonGENIE_data_clinical.txt: Please double check your SEQ_ASSAY_ID columns, there are empty rows.\n"
        else:
            total_error += "nonGENIE_data_clinical.txt: File must have SEQ_ASSAY_ID column.\n"

        #CHECK: PATIENT_ID
        haveColumn = process_functions.checkColExist(clinicalDF, 'PATIENT_ID')
        if not haveColumn:
            total_error += "nonGENIE_data_clinical.txt: File must have PATIENT_ID column.\n"
        else:
            if sum(clinicalDF['PATIENT_ID'].isnull()) > 0:
                total_error += "nonGENIE_data_clinical.txt: There can't be any blank values for PATIENT_ID\n"

        return(total_error, warning)