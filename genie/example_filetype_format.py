"""TODO: Rename this to model.py
This contains the GENIE model objects
"""
from abc import ABCMeta
from dataclasses import dataclass
import logging
import os
from typing import List, Optional

import pandas as pd
import synapseclient

logger = logging.getLogger(__name__)


@dataclass
class ValidationResults:
    """Validation results"""

    errors: str
    warnings: str
    detailed: Optional[str] = None

    def is_valid(self) -> bool:
        """True if file is valid"""
        return self.errors == ""

    def collect_errors_and_warnings(self) -> str:
        """Aggregates error and warnings into a string.

        Returns:
            str: A message containing errors and warnings.
        """
        # Complete error message
        message = "----------------ERRORS----------------\n"
        if self.errors == "":
            message = "YOUR FILE IS VALIDATED!\n"
            logger.info(message)
        else:
            for error in self.errors.split("\n"):
                if error != "":
                    logger.error(error)
            message += self.errors
        if self.warnings != "":
            for warning in self.warnings.split("\n"):
                if warning != "":
                    logger.warning(warning)
            message += "-------------WARNINGS-------------\n" + self.warnings
        return message


class FileTypeFormat(metaclass=ABCMeta):
    _process_kwargs = ["newPath", "databaseSynId"]

    _fileType = "fileType"

    _validation_kwargs: List[str] = []

    def __init__(
        self,
        syn: synapseclient.Synapse,
        center: str,
        genie_config: Optional[dict] = None,
        ancillary_files: Optional[List[List[synapseclient.Entity]]] = None,
    ):
        """A validator helper class for a center's files.

        Args:
            syn (synapseclient.Synapse): a synapseclient.Synapse object
            center (str): The participating center name.
            genie_config (dict): The configurations needed for the GENIE codebase.
                GENIE table type/name to Synapse Id. Defaults to None.
            ancillary_files (List[List[synapseclient.Entity]]): all files downloaded for validation. Defaults to None.
        """
        self.syn = syn
        self.center = center
        self.genie_config = genie_config
        self.ancillary_files = ancillary_files

        # self.pool = multiprocessing.Pool(poolSize)

    def _get_dataframe(self, filePathList):
        """
        This function by defaults assumes the filePathList is length of 1
        and is a tsv file.  Could change depending on file type.

        Args:
            filePathList:  A list of file paths (Max is 2 for the two
                           clinical files)

        Returns:
            df: Pandas dataframe of file
        """
        filePath = filePathList[0]
        df = pd.read_csv(filePath, sep="\t", comment="#")
        return df

    def read_file(self, filePathList):
        """
        Each file is to be read in for validation and processing.
        This is not to be changed in any functions.

        Args:
            filePathList:  A list of file paths (Max is 2 for the two
                           clinical files)

        Returns:
            df: Pandas dataframe of file
        """
        df = self._get_dataframe(filePathList)
        return df

    def _validateFilename(self, filePath):
        """
        Function that changes per file type for validating its filename
        Expects an assertion error.

        Args:
            filePath: Path to file
        """
        # assert True
        raise NotImplementedError

    def validateFilename(self, filePath):
        """
        Validation of file name.  The filename is what maps the file
        to its validation and processing.

        Args:
            filePath: Path to file

        Returns:
            str: file type defined by self._fileType
        """
        self._validateFilename(filePath)
        return self._fileType

    def process_steps(self, df, **kwargs):
        """
        This function is modified for every single file.
        It reformats the file and stores the file into database and Synapse.
        """
        pass

    def preprocess(self, newpath):
        """
        This is for any preprocessing that has to occur to the entity name
        to add to kwargs for processing.  entity name is included in
        the new path

        Args:
            newpath: Path to file
        """
        return dict()

    def process(self, filePath, **kwargs):
        """
        This is the main processing function.

        Args:
            filePath: Path to file
            kwargs: The kwargs are determined by self._process_kwargs

        Returns:
            str: file path of processed file
        """
        preprocess_args = self.preprocess(kwargs.get("newPath"))
        kwargs.update(preprocess_args)
        mykwargs = {}
        for required_parameter in self._process_kwargs:
            assert required_parameter in kwargs.keys(), (
                "%s not in parameter list" % required_parameter
            )
            mykwargs[required_parameter] = kwargs[required_parameter]
        logger.info("PROCESSING %s" % filePath)
        # This is done because the clinical files are being merged into a list
        if self._fileType == "clinical":
            path_or_df = self.read_file(filePath)
        # If file type is vcf or maf file, processing requires a filepath
        elif self._fileType not in ["vcf", "maf", "mafSP", "md"]:
            path_or_df = self.read_file([filePath])
        else:
            path_or_df = filePath
        path = self.process_steps(path_or_df, **mykwargs)
        return path

    def _validate(self, df: pd.DataFrame, **kwargs) -> tuple:
        """
        This is the base validation function.
        By default, no validation occurs.

        Args:
            df (pd.DataFrame): A dataframe of the file
            kwargs: The kwargs are determined by self._validation_kwargs

        Returns:
            tuple: The errors and warnings as a file from validation.
                   Defaults to blank strings
        """
        errors = ""
        warnings = ""
        logger.info("NO VALIDATION for %s files" % self._fileType)
        return errors, warnings

    def _cross_validate(self, df: pd.DataFrame) -> tuple:
        """
        This is the base cross-validation function.
        By default, no cross-validation occurs.

        Args:
            df (pd.DataFrame): A dataframe of the file

        Returns:
            tuple: The errors and warnings as a file from cross-validation.
                   Defaults to blank strings
        """
        errors = ""
        warnings = ""
        logger.info("NO CROSS-VALIDATION for %s files" % self._fileType)
        return errors, warnings

    def validate(self, filePathList, **kwargs) -> ValidationResults:
        """
        This is the main validation function.
        Every file type calls self._validate, which is different.

        Args:
            filePathList: A list of file paths.
            kwargs: The kwargs are determined by self._validation_kwargs

        Returns:
            tuple: The errors and warnings as a file from validation.
        """
        mykwargs = {}
        for required_parameter in self._validation_kwargs:
            assert required_parameter in kwargs.keys(), (
                "%s not in parameter list" % required_parameter
            )
            mykwargs[required_parameter] = kwargs[required_parameter]

        errors = ""

        try:
            df = self.read_file(filePathList)
        except Exception as e:
            errors = (
                f"The file(s) ({filePathList}) cannot be read. Original error: {str(e)}"
            )
            warnings = ""

        if not errors:
            logger.info("VALIDATING %s" % os.path.basename(",".join(filePathList)))
            errors, warnings = self._validate(df, **mykwargs)
            # only cross-validate if validation passes or ancillary files exist
            # Assumes that self.ancillary_files won't be [[]] due to whats returned from
            # extract.get_center_input_files
            if not errors and (
                isinstance(self.ancillary_files, list) and self.ancillary_files
            ):
                logger.info(
                    "CROSS-VALIDATING %s" % os.path.basename(",".join(filePathList))
                )
                errors_cross_validate, warnings_cross_validate = self._cross_validate(
                    df
                )
                errors += errors_cross_validate
                warnings += warnings_cross_validate

        result_cls = ValidationResults(errors=errors, warnings=warnings)
        return result_cls
