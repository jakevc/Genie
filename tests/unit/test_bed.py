import synapseclient
import pandas as pd
import mock
import pytest
from genie.bed import bed
from genie.bedSP import bedSP


def create_mock_table(dataframe):
    table = mock.create_autospec(synapseclient.table.CsvFileTable)
    table.asDataFrame.return_value = dataframe
    return(table)


def table_query_results(*args):
    return(table_query_results_map[args])


symbols = pd.DataFrame(dict(
    hgnc_symbol=['AAK1', 'AAED1', 'AAAS', 'PINLYP', 'XRCC1'],
    chromosome_name=['2', '9', '12', '19', '19'],
    start_position=[69688532, 99401859, 53701240, 44080952, 44047192],
    end_position=[69901481, 99417585, 53718648, 44088116, 44084625]))

# This is the gene positions that all bed dataframe will be processed against
table_query_results_map = {
    ("SELECT * FROM syn11806563",): create_mock_table(symbols), }

syn = mock.create_autospec(synapseclient.Synapse)
syn.tableQuery.side_effect = table_query_results

seq_assay_id = "SAGE-Test"
new_path = "new.bed"
parentid = "synTest"
bed_class = bed(syn, "SAGE")
bedsp_class = bedSP(syn, "SAGE")


def test_perfect___process():

    expected_beddf = pd.DataFrame(dict(
        Chromosome=['2', '9', '12', '19', '19'],
        Start_Position=[69688533, 99401860, 53701241, 44084466, 44084466],
        End_Position=[69901480, 99417584, 53718647, 44084638, 44084638],
        Hugo_Symbol=['AAK1', 'AAED1', 'AAAS', 'XRCC1', 'PINLYP'],
        includeInPanel=[True, True, True, True, True],
        ID=['AAK1', 'AAED1', 'AAAS', 'XRCC1', 'foo'],
        SEQ_ASSAY_ID=['SAGE-TEST', 'SAGE-TEST',
                      'SAGE-TEST', 'SAGE-TEST', 'SAGE-TEST'],
        Feature_Type=['exon', 'exon', 'exon', 'exon', 'exon'],
        CENTER=['SAGE', 'SAGE', 'SAGE', 'SAGE', 'SAGE']))

    expected_beddf.sort_values("ID", inplace=True)
    expected_beddf.reset_index(drop=True, inplace=True)
    beddf = pd.DataFrame({
        0: ['2', '9', '12', '19', '19'],
        1: [69688533, 99401860, 53701241, 44084466, 44084466],
        2: [69901480, 99417584, 53718647, 44084638, 44084638],
        3: ['AAK1', 'AAED1', 'AAAS', 'XRCC1', 'foo'],
        4: ['d', 'd', 'd', 'd', 'd']})

    new_beddf = bed_class._process(
        beddf, seq_assay_id, new_path, parentid, createPanel=False)
    new_beddf.sort_values("ID", inplace=True)
    new_beddf.reset_index(drop=True, inplace=True)
    assert expected_beddf.equals(new_beddf[expected_beddf.columns])


def test_includeinpanel___process():
    expected_beddf = pd.DataFrame(dict(
        Chromosome=['2', '9', '12', '19'],
        Start_Position=[69688432, 1111, 53700240, 44080953],
        End_Position=[69689532, 1111, 53719548, 44084624],
        Hugo_Symbol =['AAK1',float('nan'),'AAAS',float('nan')],
        includeInPanel =[True, True, False,True],
        ID=['foo','bar','baz','boo'],
        SEQ_ASSAY_ID=['SAGE-TEST','SAGE-TEST','SAGE-TEST','SAGE-TEST'],
        Feature_Type=['exon','intergenic','exon','exon'],
        CENTER=['SAGE','SAGE','SAGE','SAGE']))

    expected_beddf.sort_values("Chromosome",inplace=True)
    expected_beddf.reset_index(drop=True, inplace=True)

    #symbols that can't be map should be null, includeInPanel column should be included if it exists
    beddf = pd.DataFrame({0:['2', '9', '12', '19'],
                          1:[69688432, 1111, 53700240, 44080953],
                          2:[69689532, 1111, 53719548, 44084624],
                          3:['foo','bar','baz', 'boo'],
                          4:[True, True, False, True]})

    new_beddf = bedsp_class._process(beddf, seq_assay_id, new_path, parentid, createPanel=False)
    new_beddf.sort_values("Chromosome",inplace=True)
    new_beddf.reset_index(drop=True, inplace=True)
    assert expected_beddf.equals(new_beddf[expected_beddf.columns])

def test_filetype():
    assert bed_class._fileType == "bed"
    assert bedsp_class._fileType == "bedSP"

def test_incorrect_validatefilename():
    with pytest.raises(AssertionError):
        bed_class.validateFilename(['foo'])
        bed_class.validateFilename(['SAGE-test.txt'])
        bedsp_class.validateFilename(['foo'])
        bedsp_class.validateFilename(['nonGENIE_SAGE-test.txt'])

def test_correct_validatefilename():
    assert bed_class.validateFilename(["SAGE-test.bed"]) == "bed"
    assert bedsp_class.validateFilename(["nonGENIE_SAGE-test.bed"]) == "bedSP"


def test_perfect__validate():
    bedDf = pd.DataFrame(dict(a =['2', '9', '12'],
                              b =[69688533, 99401860, 53701241],
                              c =[69901480, 99417584, 53718647],
                              d =['AAK1','AAED1','AAAS'],
                              e =[True, True, True]))

    error, warning = bed_class._validate(bedDf)
    assert error == ""
    assert warning == ""    

def test_90percent_boundary__validate():
    bedDf = pd.DataFrame(dict(a =['2', '9', '12'],
                              b =[69688432, 99416585, 53700240],
                              c =[69689532, 99417685, 53719548],
                              d =['AAK1','AAED1','AAAS'],
                              e =[True, True, True]))
    error, warning = bed_class._validate(bedDf)
    assert error == ""
    assert warning == ""

def test_missingcols_failure__validate():
    bedDf = pd.DataFrame(dict(b =[69688533, 99401860, 53701241],
                              c =[69901480, 99417584, 53718647],
                              d =['AAK1','AAED1','AAAS']))

    error, warning = bed_class._validate(bedDf)
    expected_errors = ("Your BED file must at least have four columns in this order: Chromosome, Start_Position, End_Position, Hugo_Symbol.  Make sure there are no headers in your BED file.\n")
    assert error == expected_errors
    assert warning == ""


def test_hugosymbol_failure__validate():
    bedDf = pd.DataFrame(dict(a =['2', '9', '12'],
                              b =[69688533, 99401860, 53701241],
                              c =[69901480, 99417584, 53718647],
                              d =['+',float('nan'),'AAAS']))
    error, warning = bed_class._validate(bedDf)
    expected_errors = ("You cannot submit any null symbols.\n"
                      "Fourth column must be the Hugo_Symbol column, not the strand column\n")
    assert error == expected_errors
    assert warning == ""

def test_integer_failure__validate():
    bedDf = pd.DataFrame(dict(a =['2', '9', '12'],
                              b =['69688533', 99401860, 53701241],
                              c =[69901480, '99417584', 53718647],
                              d =['AAK1','AAED1','AAAS']))

    error, warning = bed_class._validate(bedDf)
    expected_errors = ("The Start_Position column must only be integers. Make sure there are no headers in your BED file.\n"
                      "The End_Position column must only be integers. Make sure there are no headers in your BED file.\n")
    assert error == expected_errors
    assert warning == ""

def test_90percentboundary_failure__validate():
    #Test 90% boundary failure boundary, with incorrect gene names
    bedDf = pd.DataFrame(dict(a =['2', '9', '12'],
                              b =[69901381, 4345, 11111],
                              c =[69911481, 99417590, 11113],
                              d =['foo','foo','AAAS']))

    error, warning = bedsp_class._validate(bedDf)
    expected_errors = ("You have no correct gene symbols. Make sure your gene symbol column (4th column) is formatted like so: SYMBOL(;optionaltext).  Optional text can be semi-colon separated.\n")
    expected_warnings = ("Any gene names that can't be remapped will be null.\n")
    assert error == expected_errors
    assert warning == expected_warnings

def test_overlapping__validate():
    #Test overlapping boundary with correct gene names
    bedDf = pd.DataFrame(dict(a =['2', '9'],
                              b =[1111, 4345],
                              c =[69880186, 99417590],
                              d =['AAK1','AAED1']))

    error, warning = bedsp_class._validate(bedDf)
    assert error == ""
    assert warning == ""

def test_symbolnull_failure__validate():
    #Test 2 gene symbols returned NULL
    bedDf = pd.DataFrame(dict(a =['19'],
                              b =[44080953],
                              c =[44084624],
                              d =['AAK1']))

    error, warning = bedsp_class._validate(bedDf)
    expected_errors = ("You have no correct gene symbols. Make sure your gene symbol column (4th column) is formatted like so: SYMBOL(;optionaltext).  Optional text can be semi-colon separated.\n")
    expected_warnings = ("Any gene names that can't be remapped will be null.\n")
    assert error == expected_errors
    assert warning == expected_warnings
