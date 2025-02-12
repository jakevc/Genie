"""Write invalid reasons"""
import logging
import os

import pandas as pd
import synapseclient

from genie import extract

logger = logging.getLogger(__name__)


def write(
    syn: synapseclient.Synapse, center_mapping_synid: str, error_tracker_synid: str
):
    """Write center errors to a file

    Args:
        syn (synapseclient.Synapse): Synapse connection
        center_mapping_synid (str): Center mapping Synapse id
        error_tracker_synid (str): Error tracking Synapse id

    """
    center_mapping_df = extract.get_syntabledf(
        syn=syn,
        query_string=f"SELECT * FROM {center_mapping_synid} where release is true",
    )
    center_errors = get_center_invalid_errors(syn, error_tracker_synid)
    for center in center_mapping_df["center"]:
        logger.info(center)
        staging_synid = center_mapping_df["stagingSynId"][
            center_mapping_df["center"] == center
        ][0]
        with open(center + "_errors.txt", "w") as errorfile:
            if center not in center_errors:
                errorfile.write("No errors!")
            else:
                errorfile.write(center_errors[center])

        ent = synapseclient.File(center + "_errors.txt", parentId=staging_synid)
        syn.store(ent)
        os.remove(center + "_errors.txt")


def _combine_center_file_errors(
    syn: synapseclient.Synapse, center_errorsdf: pd.DataFrame
) -> str:
    """Combine all center errors into one printable string

    Args:
        syn (synapseclient.Synapse): Synapse connection
        center_errorsdf (pd.DataFrame): Center errors dataframe

    Returns:
        str: Center errors in a pretty formatted string

    """
    center_errors = ""
    for _, row in center_errorsdf.iterrows():
        ent = syn.get(row["id"], downloadFile=False)
        file_errors = row["errors"].replace("|", "\n")
        error_text = f"\t{ent.name} ({ent.id}):\n\n{file_errors}\n\n"
        center_errors += error_text
    return center_errors


def get_center_invalid_errors(
    syn: synapseclient.Synapse, error_tracker_synid: str
) -> dict:
    """Get all invalid errors per center

    Args:
        syn (synapseclient.Synapse): Synapse connection
        error_tracker_synid (str): Synapse id of invalid error database table

    Returns:
        dict: {center: file error string}

    """
    error_tracker = syn.tableQuery(f"SELECT * FROM {error_tracker_synid}")
    error_trackerdf = error_tracker.asDataFrame()
    center_errorsdf = error_trackerdf.groupby("center")
    center_error_map = {}
    for center, df in center_errorsdf:
        center_error_map[center] = _combine_center_file_errors(syn, df)
    return center_error_map
