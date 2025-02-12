from unittest.mock import patch

import pandas as pd
import pytest

from genie import process_functions, validate
import genie_registry.maf
from genie_registry.maf import maf


@pytest.fixture
def maf_class(syn):
    return maf(syn, "SAGE")


@pytest.fixture
def valid_maf_df():
    yield pd.DataFrame(
        dict(
            CHROMOSOME=[1, 2, 3, 4, 5],
            START_POSITION=[1, 2, 3, 4, 2],
            REFERENCE_ALLELE=["A", "A", "A", "A", "A"],
            TUMOR_SAMPLE_BARCODE=[
                "GENIE-SAGE-ID1-1",
                "GENIE-SAGE-ID1-1",
                "GENIE-SAGE-ID1-1",
                "GENIE-SAGE-ID1-1",
                "GENIE-SAGE-ID1-1",
            ],
            T_ALT_COUNT=[1, 2, 3, 4, 3],
            T_DEPTH=[1, 2, 3, 4, 3],
            T_REF_COUNT=[1, 2, 3, 4, 3],
            N_DEPTH=[1, 2, 3, float("nan"), 3],
            N_REF_COUNT=[1, 2, 3, 4, 3],
            N_ALT_COUNT=[1, 2, 3, 4, 3],
            TUMOR_SEQ_ALLELE2=["A", "A", "A", "A", "A"],
        )
    )


def test_invalidname_validateFilename(maf_class):
    with pytest.raises(AssertionError):
        maf_class.validateFilename(["foo"])


def test_valid_validateFilename(maf_class):
    assert maf_class.validateFilename(["data_mutations_extended_SAGE.txt"]) == "maf"


def test_perfect_validation(maf_class, valid_maf_df):
    error, warning = maf_class._validate(valid_maf_df)
    assert error == ""
    assert warning == ""


def test_firstcolumn_validation(maf_class):
    """Tests if first column isn't correct"""
    mafDf = pd.DataFrame(
        {
            "REFERENCE_ALLELE": ["A", "B", "C", "D", "E"],
            "START_POSITION": [1, 2, 3, 4, 2],
            "CHROMOSOME": ["1", "2", "3", "4", "5"],
            "TUMOR_SAMPLE_BARCODE": [
                "GENIE-SAGE-ID1-1",
                "GENIE-SAGE-ID1-1",
                "GENIE-SAGE-ID1-1",
                "GENIE-SAGE-ID1-1",
                "GENIE-SAGE-ID1-1",
            ],
            "T_ALT_COUNT": [1, 2, 3, 4, 3],
            "T_DEPTH": [1, 2, 3, 4, 3],
            "T_REF_COUNT": [1, 2, 3, 4, 3],
            "N_DEPTH": [1, 2, 3, 4, 3],
            "N_REF_COUNT": [1, 2, 3, 4, 3],
            "N_ALT_COUNT": [1, 2, 3, 4, 3],
            "TUMOR_SEQ_ALLELE2": ["A", "A", "A", "A", "A"],
        }
    )
    order = [
        "REFERENCE_ALLELE",
        "START_POSITION",
        "CHROMOSOME",
        "TUMOR_SAMPLE_BARCODE",
        "T_ALT_COUNT",
        "T_DEPTH",
        "T_REF_COUNT",
        "N_DEPTH",
        "N_REF_COUNT",
        "N_ALT_COUNT",
        "TUMOR_SEQ_ALLELE2",
    ]
    error, warning = maf_class._validate(mafDf[order])
    expectedErrors = (
        "maf: First column header must be "
        "one of these: CHROMOSOME, HUGO_SYMBOL, "
        "TUMOR_SAMPLE_BARCODE.\n"
    )
    assert error == expectedErrors
    assert warning == ""


def test_missingcols_validation(maf_class):
    """Tests missing columns"""
    emptydf = pd.DataFrame()
    error, warning = maf_class._validate(emptydf)
    expected_errors = (
        "maf: Must at least have these headers: "
        "CHROMOSOME,START_POSITION,REFERENCE_ALLELE,"
        "TUMOR_SAMPLE_BARCODE,T_ALT_COUNT,"
        "TUMOR_SEQ_ALLELE2. "
        "If you are writing your maf file with R, please make"
        "sure to specify the 'quote=FALSE' parameter.\n"
        "maf: If missing T_DEPTH, must have T_REF_COUNT!\n"
    )
    expected_warnings = (
        "maf: Does not have the column headers "
        "that can give extra information to the processed "
        "maf: T_REF_COUNT, N_DEPTH, N_REF_COUNT, "
        "N_ALT_COUNT.\n"
    )
    assert error == expected_errors
    assert warning == expected_warnings


def test_errors_validation(maf_class):
    mafDf = pd.DataFrame(
        dict(
            CHROMOSOME=[1, "chr2", "WT", 4, 5],
            START_POSITION=[1, 2, 3, 4, 2],
            REFERENCE_ALLELE=["NA", float("nan"), "A", "A", "A"],
            TUMOR_SAMPLE_BARCODE=["ID1-1", "ID1-1", "ID1-1", "ID1-1", "ID1-1"],
            TUMOR_SEQ_ALLELE2=["B", "B", "B", "B", "B"],
            T_ALT_COUNT=[1, 2, 3, 4, 3],
            T_DEPTH=[1, 2, 3, 4, 3],
            N_REF_COUNT=[1, 2, 3, 4, 3],
            N_ALT_COUNT=[1, 2, 3, 4, 3],
        )
    )

    error, warning = maf_class._validate(mafDf)

    expectedErrors = (
        "maf: "
        "REFERENCE_ALLELE can't have any blank or null values.\n"
        "maf: Should not have the chr prefix in front of chromosomes.\n"
        "maf: Please double check your CHROMOSOME column.  "
        "This column must only be these values: 1, 2, 3, 4, 5, 6, 7, 8, 9, "
        "10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, X, Y, MT\n"
        "maf: TUMOR_SAMPLE_BARCODE must start with GENIE-SAGE\n"
    )
    expectedWarnings = (
        "maf: "
        "Does not have the column headers that can give "
        "extra information to the processed maf: "
        "T_REF_COUNT, N_DEPTH.\n"
        "maf: "
        "REFERENCE_ALLELE column contains 'NA' values, "
        "which cannot be placeholders for blank values.  "
        "Please put in empty strings for blank values.\n"
    )

    assert error == expectedErrors
    assert warning == expectedWarnings


def test_invalid_validation(maf_class):
    mafDf = pd.DataFrame(
        dict(
            CHROMOSOME=[1, 2, 3, 4, 2, 4],
            T_ALT_COUNT=[1, 2, 3, 4, 3, 4],
            START_POSITION=[1, 2, 3, 4, 2, 4],
            REFERENCE_ALLELE=["A ", "A ", "A", "A ", "A ", " A"],
            TUMOR_SAMPLE_BARCODE=["ID1-1", "ID1-1", "ID1-1", "ID1-1", "ID1-1", "ID1-1"],
            N_DEPTH=[1, 2, 3, 4, 3, 4],
            N_REF_COUNT=[1, 2, 3, "string", 3, 4],
            N_ALT_COUNT=[1, 2, 3, 4, 3, 4],
            TUMOR_SEQ_ALLELE2=["NA", float("nan"), " A", "A ", " A", " A"],
        )
    )

    with patch.object(
        genie_registry.maf, "_check_tsa1_tsa2", return_value=""
    ) as check_tsa1_tsa2:
        error, warning = maf_class._validate(mafDf)
        check_tsa1_tsa2.assert_called_once_with(mafDf)
    expectedErrors = (
        "maf: Must not have duplicated variants. "
        "Samples with duplicated variants: ID1-1\n"
        "maf: "
        "If missing T_DEPTH, must have T_REF_COUNT!\n"
        "maf: N_REF_COUNT must be a numerical column.\n"
        "maf: "
        "TUMOR_SEQ_ALLELE2 can't have any blank or null values.\n"
        "maf: TUMOR_SAMPLE_BARCODE must start with GENIE-SAGE\n"
    )
    expectedWarnings = (
        "maf: TUMOR_SEQ_ALLELE2 column contains 'NA' values, "
        "which cannot be placeholders for blank values.  "
        "Please put in empty strings for blank values.\n"
        "maf: Does not have the column headers that can give "
        "extra information to the processed maf: T_REF_COUNT.\n"
    )
    assert error == expectedErrors
    assert warning == expectedWarnings


@pytest.mark.parametrize("col", ["temp", "REFERENCE_ALLELE"])
def test_noerror__check_allele_col(col):
    """Test error and warning is an empty string if REF col isn't passed in"""
    df = pd.DataFrame(dict(REFERENCE_ALLELE=["A", "A"]))
    error, warning = genie_registry.maf._check_allele_col(df, col)
    assert error == ""
    assert warning == ""


def test_warning__check_allele_col():
    """Test warning occurs when 'NA' string is passed in"""
    df = pd.DataFrame(dict(TEMP=["NA", "A"]))
    error, warning = genie_registry.maf._check_allele_col(df, "TEMP")
    assert error == ""
    assert warning == (
        "maf: "
        "TEMP column contains 'NA' values, "
        "which cannot be placeholders for blank values.  "
        "Please put in empty strings for blank values.\n"
    )


def test_error__check_allele_col():
    """Test error occurs when blank allele is passed in"""
    df = pd.DataFrame(dict(TEMP=[float("nan"), "A"]))
    error, warning = genie_registry.maf._check_allele_col(df, "TEMP")
    assert error == ("maf: TEMP can't have any blank or null values.\n")
    assert warning == ""


def test_invalid__check_tsa1_tsa2():
    """Test the scenario in which maf file has TSA1 and TSA2 and fails"""
    df = pd.DataFrame(
        dict(
            REFERENCE_ALLELE=["A", "A", "A"],
            TUMOR_SEQ_ALLELE1=["B", "B", "B"],
            TUMOR_SEQ_ALLELE2=["C", "C", "C"],
        )
    )
    error = genie_registry.maf._check_tsa1_tsa2(df)
    assert error == (
        "maf: Contains both "
        "TUMOR_SEQ_ALLELE1 and TUMOR_SEQ_ALLELE2 columns. "
        "All values in TUMOR_SEQ_ALLELE1 must match all values in "
        "REFERENCE_ALLELE or all values in TUMOR_SEQ_ALLELE2.\n"
    )


@pytest.mark.parametrize(
    "df",
    [
        pd.DataFrame(
            dict(
                REFERENCE_ALLELE=["A", "A", "A"],
                TUMOR_SEQ_ALLELE1=["C", "C", "C"],
                TUMOR_SEQ_ALLELE2=["C", "C", "C"],
            )
        ),
        pd.DataFrame(
            dict(
                REFERENCE_ALLELE=["C", "C", "C"],
                TUMOR_SEQ_ALLELE1=["C", "C", "C"],
                TUMOR_SEQ_ALLELE2=["A", "A", "A"],
            )
        ),
    ],
)
def test_valid__check_tsa1_tsa2(df):
    """Test valid TSA1 and TSA2"""
    error = genie_registry.maf._check_tsa1_tsa2(df)
    assert error == ""


def test_that__cross_validate_does_not_read_files_if_no_clinical_files(maf_class):
    with patch.object(
        validate,
        "parse_file_info_in_nested_list",
        return_value={"files": {}, "file_info": {"name": "", "path": ""}},
    ) as patch_clinical_files, patch.object(
        process_functions,
        "get_clinical_dataframe",
    ) as patch_get_df:
        errors, warnings = maf_class._cross_validate(pd.DataFrame({}))
        assert warnings == ""
        assert errors == ""
        patch_get_df.assert_not_called()


def test_that__cross_validate_does_not_call_check_col_exist_if_clinical_df_read_error(
    maf_class,
):
    with patch.object(
        validate,
        "parse_file_info_in_nested_list",
        return_value={"files": {"some_file"}, "file_info": {"name": "", "path": ""}},
    ) as patch_clinical_files, patch.object(
        process_functions,
        "get_clinical_dataframe",
        side_effect=Exception("mocked error"),
    ) as patch_get_df, patch.object(
        process_functions, "checkColExist"
    ) as patch_check_col_exist:
        errors, warnings = maf_class._cross_validate(pd.DataFrame({}))
        assert warnings == ""
        assert errors == ""
        patch_check_col_exist.assert_not_called()


def test_that__cross_validate_does_not_call_check_values_if_id_cols_do_not_exist(
    maf_class,
):
    with patch.object(
        validate,
        "parse_file_info_in_nested_list",
        return_value={"files": {"some_file"}, "file_info": {"name": "", "path": ""}},
    ) as patch_clinical_files, patch.object(
        process_functions,
        "get_clinical_dataframe",
        return_value=pd.DataFrame({"test_col": [2, 3, 4]}),
    ) as patch_get_df, patch.object(
        process_functions, "checkColExist", return_value=False
    ) as patch_check_col_exist, patch.object(
        validate, "check_values_between_two_df"
    ) as patch_check_values:
        errors, warnings = maf_class._cross_validate(pd.DataFrame({}))
        assert warnings == ""
        assert errors == ""
        patch_check_values.assert_not_called()


@pytest.mark.parametrize(
    "test_clinical_df,expected_error,expected_warning",
    [
        (
            pd.DataFrame(
                dict(
                    SAMPLE_ID=[
                        "GENIE-SAGE-ID1-0",
                        "GENIE-SAGE-ID1-2",
                    ],
                )
            ),
            "At least one TUMOR_SAMPLE_BARCODE in your MAF file does not exist as a SAMPLE_ID in your sample clinical file. "
            "Please update your file(s) to be consistent.\n",
            "",
        ),
        (
            pd.DataFrame(
                dict(
                    SAMPLE_ID=[
                        "GENIE-SAGE-ID1-1",
                        "GENIE-SAGE-ID1-1",
                    ],
                )
            ),
            "",
            "",
        ),
    ],
    ids=["diff_ids", "matching_ids"],
)
def test_that__cross_validate_returns_expected_msg_if_valid(
    maf_class, valid_maf_df, test_clinical_df, expected_warning, expected_error
):
    with patch.object(
        validate,
        "parse_file_info_in_nested_list",
        return_value={
            "files": {"some_file"},
            "file_info": {"name": "data_clinical_supp.txt", "path": ""},
        },
    ) as patch_clinical_files, patch.object(
        process_functions,
        "get_clinical_dataframe",
        return_value=test_clinical_df,
    ) as patch_get_df:
        errors, warnings = maf_class._cross_validate(mutationDF=valid_maf_df)
        assert warnings == expected_warning
        assert errors == expected_error
