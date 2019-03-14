import synapseclient
from synapseclient import File, Table
import os
import pandas as pd
import re
import logging
import json
import httplib2 as http
import datetime
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from Crypto.PublicKey import RSA
import ast
# try:
#   from urllib.request import urlopen
# except ImportError:
#   from urllib2 import urlopen
#Ignore SettingWithCopyWarning warning
pd.options.mode.chained_assignment = None

logger = logging.getLogger(__name__)

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


# try:
#   from urlparse import urlparse
# except ImportError:
#   from urllib.parse import urlparse

# Create merged dictionary of remapped genes
# def createDict(invalidated_genes):
#     toRemapRemove = {}
#     invalidated_genes = pd.Series(invalidated_genes)
#     for i in invalidated_genes[invalidated_genes!=True]:
#         toRemapRemove.update(i)
#     return(toRemapRemove)

#Validate genes
# def hgncRestCall(path):
#     """
#     This function does the rest call to the genenames website

#     :params path:     The gene symbol url path to add to the base uri

#     :returns:         If the symbol exists, returns True and the corrected symbol, otherwise returns False and None.
#     """
#     headers = {'Accept': 'application/json',}

#     uri = 'http://rest.genenames.org'

#     target = urlparse(uri+path)
#     method = 'GET'
#     body = ''
#     h = http.Http()
#     response, content = h.request(target.geturl(),
#                                   method,
#                                   body,
#                                   headers)
#     if response['status'] == '200':
#         data = json.loads(content)
#         if len(data['response']['docs']) == 0:
#             return(False, [None])
#         else:
#             mapped = [symbol['symbol'] for symbol in data['response']['docs']]
#             return(True, mapped)
#     else:
#         return(False, [None])

# Validation of gene names
# def validateSymbol(gene, returnMapping=False):
#     """
#     This function does validation of symbols

#     :params gene:               Gene symbol
#     :params returnMapping:      Return mapping of old gene to new gene

#     :returns:                   Check if the provided gene name is a correct symbol and print out genes 
#                                 that need to be remapped or can't be mapped to anything
#     """
#     path = '/fetch/symbol/%s' %  gene
#     verified, symbol = hgncRestCall(path)
#     if not verified:
#         path = '/fetch/prev_symbol/%s' %  gene
#         verified, symbol = hgncRestCall(path)
#     if not verified:
#         path = '/fetch/alias_symbol/%s' %  gene
#         verified, symbol = hgncRestCall(path)       
#     if gene in symbol:
#         return(True)
#     else:
#         if symbol[0] is None:
#             #logger.error("%s cannot be remapped. Please correct." % gene)
#             logger.warning("%s cannot be remapped. These rows will have an empty gene symbol" % gene)
#         else:
#             #if "MLL4", then the HUGO symbol should be KMT2D and KMT2B
#             if len(symbol) > 1:
#                 #logger.error("%s can be mapped to different symbols: %s. Please correct." % (gene, ", ".join(symbol)))
#                 logger.warning("%s can be mapped to different symbols: %s. Please correct or it will be removed." % (gene, ", ".join(symbol)))
#             else:
#                 logger.info("%s will be remapped to %s" % (gene, symbol[0]))
#                 if returnMapping:
#                     return({gene: symbol[0]})
#                 else:
#                     return(True)
#         if returnMapping:
#             return({gene: pd.np.nan})
#         else:
#             return(False)
#         #return(True)

# # Remap and remove genes in dataframes given a column
# def remapGenes(invalidated_genes, DF, col,isBedFile=False):
#     nonmapped = []
#     gene_dict = createDict(invalidated_genes)
#     for key in gene_dict:
#         value = gene_dict[key]
#         if isBedFile:
#         #     nonmapped.append(key)
#         #     DF = DF[DF[col] != key]
#         # else:
#             DF[col][DF[col] == key] = value
#     return(DF, nonmapped)

def retry_get_url(url):
    '''
    Implement retry logic when getting urls.  Timesout at 3 seconds, retries 5 times.

    Args:
        url:  Http or https url

    Returns:
        requests.get()
    '''
    s = requests.Session()
    retries = Retry(total=5, backoff_factor=1)
    s.mount('http://', HTTPAdapter(max_retries=retries))
    s.mount('https://', HTTPAdapter(max_retries=retries))
    response = s.get(url, timeout=3)
    return(response)

# Check if oncotree link is live
def checkUrl(url):
    temp = retry_get_url(url)
    assert temp.status_code == 200, "%s site is down"% url

# VALIDATION: Getting the GENIE mapping synapse tables
def getGenieMapping(syn, synId):
    """
    This function gets the GENIE mapping tables
    
    :params synId:          Synapse Id of synapse table

    :returns:               Table dataframe
    """
    table_ent = syn.tableQuery('SELECT * FROM %s' %synId)
    table = table_ent.asDataFrame()
    table = table.fillna("")
    return(table)

# VALIDATION: Check if the column exists
def checkColExist(DF, key):
    """
    This function checks if the key exists as a header in a dataframe
    
    :params DF:             Pandas dataframe
    :params key:            Expected header column name

    :returns:               An error message or an empty string
    """
    result = False if DF.get(key) is None else True
    return(result)

# VALIDATION: get oncotree codes from oncotree URL
def get_oncotree_codes(oncotree_url): 
    """ Gets the oncotree data from the specified url """
    #PATTERN = re.compile('([A-Za-z\' ,-/]*) \\(([A-Za-z_]*)\\)')
    PATTERN = re.compile('.*[(](.*)[)]')
    # with requests.get(oncotree_url) as oncotreeUrl:
    #   oncotree = oncotreeUrl.text.split("\n")
    oncotreeUrl = retry_get_url(oncotree_url)
    oncotree = oncotreeUrl.text.split("\n")

    #oncotree = urlopen(oncotree_url).read().split('\n')
    allCodes = []
    for row in oncotree[:-1]:
        data = row.split("\t")
        allCodes.extend([PATTERN.match(i).group(1) for i in data[0:5] if PATTERN.match(i)])
    codes = pd.DataFrame({"ONCOTREE_CODE":list(set(allCodes))})
    return(codes)

def getDatabaseSynId(syn, tableName, test=False, databaseToSynIdMappingDf=None):
    if databaseToSynIdMappingDf is None:
        if test:
            databaseToSynIdMapping = syn.tableQuery('SELECT * FROM syn11600968')
        else:
            databaseToSynIdMapping = syn.tableQuery('SELECT * FROM syn10967259')

        databaseToSynIdMappingDf = databaseToSynIdMapping.asDataFrame()
        synId = databaseToSynIdMappingDf.Id[databaseToSynIdMappingDf['Database'] == tableName]
    else:
        synId = databaseToSynIdMappingDf.Id[databaseToSynIdMappingDf['Database'] == tableName]
    return(synId.values[0])

def rmFiles(folderPath, recursive=True):
    for dirPath, dirNames, filePaths in os.walk(folderPath):
        for filePath in filePaths:
            os.unlink(os.path.join(dirPath, filePath))
        if not recursive:
            break

#Remove .0
def removeFloat(df):
    text = df.to_csv(sep="\t",index=False)
    text = text.replace(".0\t","\t")
    text = text.replace(".0\n","\n")
    return(text)

#remove string float
def removeStringFloat(string):
    string = string.replace(".0\t","\t")
    string = string.replace(".0\n","\n")
    return(string)

#remove decimal for integers due to pandas
def removePandasDfFloat(df):
    text = df.to_csv(sep="\t",index=False)
    text = removeStringFloat(text)
    return(text)


########################################################################
# Check if GENIE ID is labelled correctly
########################################################################
def checkGenieId(ID,center):
    if str(ID).startswith("%s-" % center):
        return('GENIE-%s' % str(ID))
    elif not str(ID).startswith('GENIE-%s-' % center):
        return('GENIE-%s-%s' % (center, str(ID)))
    else:
        return(str(ID))

########################################################################
#Storing Files along with annotations
########################################################################
def storeFile(syn, fileName, parentId, center, fileFormat, dataSubType, platform=None, cBioFileFormat=None, used=None):
    logger.info("STORING FILES")
    fileEnt = File(fileName, parent = parentId)
    fileEnt.center = center
    fileEnt.species = "Human"
    fileEnt.consortium = 'GENIE'
    fileEnt.dataType = "genomicVariants"
    fileEnt.fundingAgency = "AACR"
    fileEnt.assay = 'targetGeneSeq'
    fileEnt.fileFormat = fileFormat
    fileEnt.dataSubType = dataSubType
    fileEnt.fileStage = "staging"
    fileEnt.platform = platform
    if platform is not None:
        fileEnt.platform = platform
    if cBioFileFormat is not None:
        fileEnt.cBioFileFormat = cBioFileFormat
    ent = syn.store(fileEnt,used = used)
    return(ent)

########################################################################
# SEQ_DATE FILTER
########################################################################

# SEQ_DATE - Clinical data (6 and 12 as parameters)
# Jan-2017 , given processing date (today) -> staging release (processing date - Jan-2017 < 6 months)
# July-2016 , given processing date (today) -> consortium release (processing date - July-2016 between 6 months - 12 months)
def seqDateFilter(clinicalDf, processingDate, days):
    copyClinicalDf = clinicalDf.copy()
    #copyClinicalDf['SEQ_DATE'][copyClinicalDf['SEQ_DATE'].astype(str) == '999'] = "Jan-1988"
    #copyClinicalDf['SEQ_DATE'][copyClinicalDf['SEQ_DATE'].astype(str) == '999.0'] = "Jan-1988"
    if not isinstance(processingDate, datetime.datetime):
        processingDate = datetime.datetime.strptime(processingDate, '%b-%Y')
    #Remove this null statement after clinical files have been re-validated
    #copyClinicalDf['SEQ_DATE'][copyClinicalDf['SEQ_DATE'].isnull()] = "Jan-1900"
    copyClinicalDf['SEQ_DATE'][copyClinicalDf['SEQ_DATE'] == "Release"] = "Jan-1900"
    #clinicalDf['SEQ_DATE'][clinicalDf['SEQ_DATE'] == '999'] = "Jan-1988"
    dates = copyClinicalDf['SEQ_DATE'].apply(lambda date: datetime.datetime.strptime(date, '%b-%Y'))
    keep = processingDate - dates > datetime.timedelta(days)
    keepSamples = copyClinicalDf['SAMPLE_ID'][~keep]
    #copyClinicalDf.SEQ_DATE[keep].unique()
    return(keepSamples)
    
#Add clinical file headers
def addClinicalHeaders(clinicalDf, mapping, patientCols, sampleCols, samplePath, patientPath):
    patientLabels = [str(mapping['labels'][mapping['cbio'] == i].values[0]) for i in patientCols]
    sampleLabels = [str(mapping['labels'][mapping['cbio'] == i].values[0]) for i in sampleCols]
    patientDesc = [str(mapping['description'][mapping['cbio'] == i].values[0]) for i in patientCols]
    sampleDesc = [str(mapping['description'][mapping['cbio'] == i].values[0]) for i in sampleCols]
    patientType= [str(mapping['colType'][mapping['cbio'] == i].values[0]) for i in patientCols]
    sampleType = [str(mapping['colType'][mapping['cbio'] == i].values[0]) for i in sampleCols]
    with open(patientPath, "w+") as patientFile:
        patientFile.write("#%s\n" % "\t".join(patientLabels))
        patientFile.write("#%s\n" % "\t".join(patientDesc))
        patientFile.write("#%s\n" % "\t".join(patientType))
        patientFile.write("#%s\n" % "\t".join(['1']*len(patientLabels)))
        text = removeFloat(clinicalDf[patientCols].drop_duplicates('PATIENT_ID'))
        patientFile.write(text)
    with open(samplePath, "w+") as sampleFile:
        sampleFile.write("#%s\n" % "\t".join(sampleLabels))
        sampleFile.write("#%s\n" % "\t".join(sampleDesc))
        sampleFile.write("#%s\n" % "\t".join(sampleType))
        sampleFile.write("#%s\n" % "\t".join(['1']*len(sampleLabels)))
        text = removeFloat(clinicalDf[sampleCols].drop_duplicates("SAMPLE_ID"))
        sampleFile.write(text)

########################################################################
# CENTER ANONYMIZING
########################################################################
def center_anon(filePath, anonymizeCenterDf):
    with open(filePath, "r") as datafile:
        text = datafile.read()
    for center in anonymizeCenterDf['center']:
        newCenter = anonymizeCenterDf['newCenter'][anonymizeCenterDf['center'] == center].values[0]
        text = re.sub("\t%s\t" % center,"\t%s\t" % newCenter, text)
        text = re.sub("GENIE-%s-" % center,"GENIE-%s-" % newCenter, text)
    with open(filePath, "w") as datafile:
        datafile.write(text)

def center_convert_back(filePath, anonymizeCenterDf):
    with open(filePath, "r") as datafile:
        text = datafile.read()
    for center in anonymizeCenterDf['center']:
        newCenter = anonymizeCenterDf['newCenter'][anonymizeCenterDf['center'] == center].values[0]
        text = re.sub("\t%s\t" % newCenter,"\t%s\t" % center, text)
        text = re.sub("GENIE-%s-" % newCenter,"GENIE-%s-" % center, text)
    with open(filePath, "w") as datafile:
        datafile.write(text)

####################################################################################
# UPDATING DATABASE
####################################################################################
def _check_valid_df(df, checkby):
    '''
    Checking if variable is a pandas dataframe and column specified exist
    '''
    if not isinstance(df, pd.DataFrame):
        raise ValueError("Must pass in pandas dataframes")
    if df.get(checkby) is None:
        raise ValueError("{} column must exist in both dataframes".format(checkby))

def _get_left_diff_df(left, right, checkby):
    '''
    Subset the dataframe based on 'checkby' by taking values in the left df
    that arent in the right df

    Args:
        left: Dataframe
        right: Dataframe
        checkby: Column of values to compare

    Return:
        Dataframe: Subset of dataframe from left that don't exist in the right
    '''
    _check_valid_df(left, checkby)
    _check_valid_df(right, checkby)
    diffdf = left[~left[checkby].isin(right[checkby])]
    return(diffdf)

def _get_left_union_df(left, right, checkby):
    '''
    Subset the dataframe based on 'checkby' by taking the union of 
    values in the left df with the right df

    Args:
        left: Dataframe
        right: Dataframe
        checkby: Column of values to compare

    Return: 
        Dataframe: Subset of dataframe from left that also exist in the right
    '''
    _check_valid_df(left, checkby)
    _check_valid_df(right, checkby)
    uniondf = left[left[checkby].isin(right[checkby])]
    return(uniondf)

def _append_rows(new_datasetdf, databasedf, checkby):
    '''
    Compares the dataset from the database and determines which rows to 
    append from the dataset

    Args:
        new_datasetdf: Input data dataframe
        databasedf: Existing data dataframe
        checkby: Column of values to compare

    Return:
        Dataframe: Dataframe of rows to append
    '''
    databasedf.fillna('',inplace=True)
    new_datasetdf.fillna('',inplace=True)

    appenddf = _get_left_diff_df(new_datasetdf, databasedf, checkby)
    if not appenddf.empty:
        logger.info("Adding Rows")
    else:
        logger.info("No new rows")
    del appenddf[checkby]
    appenddf.reset_index(drop=True,inplace=True)
    return(appenddf)

def _delete_rows(new_datasetdf, databasedf, checkby):
    '''
    Compares the dataset from the database and determines which rows to
    delete from the dataset

    Args:
        new_datasetdf: Input data dataframe
        databasedf: Existing data dataframe
        checkby: Column of values to compare

    Return:
        Dataframe: Dataframe of rows to delete
    '''

    databasedf.fillna('',inplace=True)
    new_datasetdf.fillna('',inplace=True)
    #If the new dataset is empty, delete everything in the database
    deletedf = _get_left_diff_df(databasedf, new_datasetdf, checkby)
    if not deletedf.empty:
        logger.info("Deleting Rows")
        delete_rowid_version = pd.DataFrame([[rowid.split("_")[0],rowid.split("_")[1]] for rowid in deletedf.index])
        delete_rowid_version.reset_index(drop=True,inplace=True)
    else:
        delete_rowid_version = pd.DataFrame()
        logger.info("No deleted rows")
    
    #del deletedf[checkby]
    return(delete_rowid_version)

def _update_rows(new_datasetdf, databasedf, checkby):
    '''
    Compares the dataset from the database and determines which rows to
    update from the dataset

    Args:
        new_datasetdf: Input data dataframe
        databasedf: Existing data dataframe
        checkby: Column of values to compare

    Return:
        Dataframe: Dataframe of rows to update
    '''
    initial_database = databasedf.copy()
    databasedf.fillna('',inplace=True)
    new_datasetdf.fillna('',inplace=True)
    updatesetdf = _get_left_union_df(new_datasetdf, databasedf, checkby)
    updating_databasedf = _get_left_union_df(databasedf, new_datasetdf, checkby)

    #If you input the exact same dataframe theres nothing to update
    #must save row version and ids for later
    rowids = updating_databasedf.index.values
    #Set index values to be 'checkby' values
    updatesetdf.index = updatesetdf[checkby]
    updating_databasedf.index = updating_databasedf[checkby]
    #Remove duplicated index values
    updatesetdf = updatesetdf[~updatesetdf.index.duplicated()]
    #Reorder dataset index
    updatesetdf = updatesetdf.loc[updating_databasedf.index]
    #Index comparison
    differences = updatesetdf != updating_databasedf
    differentrows = differences.apply(sum, axis=1) >0

    if sum(differentrows) > 0:
        updating_databasedf.loc[differentrows] = updatesetdf.loc[differentrows]
        toupdatedf = updating_databasedf.loc[differentrows]
        del toupdatedf[checkby]
        logger.info("Updating rows")
        rowid_version = pd.DataFrame([[rowid.split("_")[0],rowid.split("_")[1]] for rowid, row in zip(rowids, differentrows) if row])
        toupdatedf['ROW_ID'] = rowid_version[0].values
        toupdatedf['ROW_VERSION'] = rowid_version[1].values
        toupdatedf.reset_index(drop=True,inplace=True)
    else:
        toupdatedf = pd.DataFrame()
        logger.info("No updated rows")

    return(toupdatedf)


def updateData(syn, databaseSynId, newData, filterBy, filterByColumn= "CENTER", col=None, toDelete=False):
    databaseEnt = syn.get(databaseSynId)
    database = syn.tableQuery("SELECT * FROM %s where %s ='%s'" % (databaseSynId, filterByColumn, filterBy))
    database = database.asDataFrame()
    if col is not None:
        database = database[col]
    else:
        newData = newData[database.columns]
    updateDatabase(syn, database, newData, databaseSynId, databaseEnt.primaryKey, toDelete)
    
def updateDatabase(syn, database, new_dataset, databaseSynId, uniqueKeyCols, toDelete=False):
    """
    Updates synapse tables by a row identifier with another dataset that has the same number and order of columns
    
    Args:
        syn: Synapse object
        database: The synapse table (pandas dataframe)
        new_dataset: New dataset (pandas dataframe)
        databaseSynId: Synapse Id of the database table
        uniqueKeyCols: Column(s) that make up the unique key
        toDelete: Delete rows, Defaults to False

    Returns:
        Nothing
    """
    checkBy = 'UNIQUE_KEY'
    database = database.fillna("")
    origDatabaseCols = database.columns
    columnOrder = ['ROW_ID','ROW_VERSION']
    columnOrder.extend(origDatabaseCols.tolist())
    new_dataset = new_dataset.fillna("")
    #Columns must be in the same order
    new_dataset = new_dataset[origDatabaseCols]
    database[uniqueKeyCols] = database[uniqueKeyCols].applymap(str)
    database[checkBy] = database[uniqueKeyCols].apply(lambda x: ' '.join(x), axis=1)
    new_dataset[uniqueKeyCols] = new_dataset[uniqueKeyCols].applymap(str)
    new_dataset[checkBy] = new_dataset[uniqueKeyCols].apply(lambda x: ' '.join(x), axis=1)

    #allRowIds = database.index.values
    allupdates = pd.DataFrame()
    appendrows = _append_rows(new_dataset, database, checkBy)
    updaterows = _update_rows(new_dataset, database, checkBy)
    if toDelete:
        deleterows = _delete_rows(new_dataset, database, checkBy)
    else:
        deleterows = pd.DataFrame()
    allupdates = allupdates.append(appendrows)
    allupdates = allupdates.append(updaterows)

    storedatabase = False
    updateAllFile = os.path.join(SCRIPT_DIR,"toUpdateAll.csv")
    with open(updateAllFile,"w") as updateFile:
        #Must write out the headers in case there are no appends or updates
        updateFile.write(",".join(columnOrder) + "\n")
        if not allupdates.empty:
            updateFile.write(allupdates[columnOrder].to_csv(index=False,header=None).replace(".0,",","))
            storedatabase = True
        if not deleterows.empty:
            updateFile.write(deleterows.to_csv(index=False,header=None).replace(".0,",","))
            storedatabase = True
    if storedatabase:
        syn.store(synapseclient.Table(databaseSynId, updateAllFile))

#Check if an item can become an integer
def checkInt(element):
    try:
        element = float(element)
        return(element.is_integer())
    except ValueError:
        return(False)

#CREATE ONCOTREE DICTIONARY MAPPING TO PRIMARY, SECONDARY, CANCER TYPE, AND CANCER DESCRIPTION
def extract_oncotree_code_mappings_from_oncotree_json(oncotree_json, primary, secondary):
    oncotree_code_to_info = {}

    data = oncotree_json['children']
    for node in data:
        # if not node['code']:
        #     sys.stderr.write('Encountered oncotree node without oncotree code : ' + node + '\n')
        #     continue
        if data[node]['level'] == 1:
            primary = node
            secondary = ''
        elif data[node]['level'] == 2:
            secondary = node
        cancer_type = data[node]['mainType']
        cancer_type_detailed = data[node]['name']
        if not cancer_type_detailed:
            cancer_type_detailed = ''
        oncotree_code_to_info[node.upper()] = { 'CANCER_TYPE' : cancer_type, 'CANCER_TYPE_DETAILED' : cancer_type_detailed , 'ONCOTREE_PRIMARY_NODE': primary, 'ONCOTREE_SECONDARY_NODE':secondary}
        if len(data[node]['children']) > 0:
            recurseDict = extract_oncotree_code_mappings_from_oncotree_json(data[node], primary, secondary)
            oncotree_code_to_info.update(recurseDict)
    return oncotree_code_to_info
    
#CREATE ONCOTREE DICTIONARY MAPPING TO PRIMARY, SECONDARY, CANCER TYPE, AND CANCER DESCRIPTION
def get_oncotree_code_mappings(oncotree_tumortype_api_endpoint_url):

    #oncotree_raw_response = urlopen(oncotree_tumortype_api_endpoint_url).text
    #with requests.get(oncotree_tumortype_api_endpoint_url) as oncotreeUrl:
    oncotreeUrl = retry_get_url(oncotree_tumortype_api_endpoint_url)
    oncotree_raw_response = oncotreeUrl.text
    oncotree_response = json.loads(oncotree_raw_response)
    oncotree_response = oncotree_response['TISSUE']
    return extract_oncotree_code_mappings_from_oncotree_json(oncotree_response, '', '')


#Get mapping code #Add USE DESCRIPTION sampletypedetailed -> public
def getCODE(mapping, key, useDescription=False):
    if useDescription:
        value = mapping['DESCRIPTION'][mapping['CODE'] == key].values
    else:
        value = mapping['CBIO_LABEL'][mapping['CODE'] == key].values
    if len(value) >0:
        return(value[0])
    else:
        return("")

def getPrimary(code, oncotreeDict, primary):
    if code != "":
        for level in oncotreeDict:
            if sum(oncotreeDict[level] == code) > 0:
                toAdd = primary[oncotreeDict[level] == code].values[0]
                break
            else: 
                toAdd = code
    else:
        toAdd = "NOT_ANNOTATED"
    return(toAdd)



# def createKey():
#   import Crypto
#   from Crypto.PublicKey import RSA
#   from Crypto import Random

#   random_generator = Random.new().read
#   key = RSA.generate(1024, random_generator) #generate public and private keys

#   #publickey = key.publickey # pub key export for exchange
#   encrypted = key.encrypt(geniePassword, 32)
#   #message to encrypt is in the above line 'encrypt this message'
#   descrypted = key.decrypt(encrypted)
#   with open("genie.pem","w") as geniePem:
#       geniePem.write(key.exportKey(format='PEM'))

## READ KEY
def read_key(pemfile_path):
    '''
    Obtain key from pemfile

    Args:
        pemfile_path:  Path to pemfile

    Returns:
        RSA key
    '''
    f = open(pemfile_path,'r')
    key = RSA.importKey(f.read())
    return(key)

def decrypt_message(message, key):
    '''
    Decrypt message with a pem key from
    func read_key

    Args:
        message: Encrypted message
        key: read_key returned key

    Returns:
        Decrypted message
    '''
    decrypted = key.decrypt(ast.literal_eval(str(message)))
    return(decrypted.decode("utf-8"))

def get_password(pemfile_path):
    '''
    Get password using pemfile

    Args:
        pemfile_path: Path to pem file

    Return:
        Password
    '''
    if not os.path.exists(pemfile_path):
        raise ValueError("Path to pemFile must be specified if there is no cached credentials")
    key = read_key(pemfile_path)
    genie_pass = decrypt_message(os.environ['GENIE_PASS'], key)
    return(genie_pass)

def synLogin(pemfile_path, debug=False):
    '''
    Use pem file to log into synapse if credentials aren't cached

    Args:
        pemfile_path: Path to pem file
        debug: Synapse debug feature.  Defaults to False

    Returns:
        Synapse object logged in
    '''
    try:
        syn = synapseclient.Synapse(debug=debug)
        syn.login()
    except:
        genie_pass = get_password(pemfile_path)
        syn = synapseclient.Synapse(debug=debug)
        syn.login(os.environ['GENIE_USER'], genie_pass)
    return(syn)
