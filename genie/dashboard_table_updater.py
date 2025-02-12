"""Updates dashboard tables"""
import argparse
import datetime
import logging
import os

import pandas as pd
import synapseclient
from synapseclient.core.utils import to_unix_epoch_time

from genie import extract, load, process_functions

logger = logging.getLogger(__name__)


def get_center_data_completion(center, df):
    """
    Gets center data completion.  Calulates the percentile of
    how complete a clinical data element is:
    Number of not blank/Unknown/NA divded by
    total number of patients or samples

    Args:
        center: GENIE center
        df: sample or patient dataframe

    Returns:
        Dataframe: Center data
    """
    centerdf = df[df["CENTER"] == center]
    total = len(centerdf)
    center_data = pd.DataFrame()
    skip_cols = [
        "CENTER",
        "PATIENT_ID",
        "SAMPLE_ID",
        "SAMPLE_TYPE_DETAILED",
        "SECONDARY_RACE",
        "TERTIARY_RACE",
    ]
    for col in centerdf:
        if col not in skip_cols:
            not_missing = [
                not pd.isnull(value) and value != "Not Collected"
                for value in centerdf[col]
            ]
            completeness = float(sum(not_missing)) / int(total)
            returned = pd.DataFrame([[col, center, total, completeness]])
            center_data = pd.concat([center_data, returned])
    return center_data


def update_samples_in_release_table(
    syn, file_mapping, release, samples_in_release_synid
):
    """
    Updates the sample in release table
    This tracks the samples of each release.  1 means it exists, and 0
    means it doesn't

    Args:
        syn: synapse object
        file_mapping: file mapping generated from file mapping function
        release:  GENIE release number (ie. 5.3-consortium)
        samples_in_release_synid: Synapse Id of 'samples in release' Table
    """
    clinical_ent = syn.get(file_mapping["sample"], followLink=True)
    clinicaldf = pd.read_csv(clinical_ent.path, sep="\t", comment="#")
    cols = [i["name"] for i in list(syn.getTableColumns(samples_in_release_synid))]

    if release not in cols:
        schema = syn.get(samples_in_release_synid)
        syn_col = synapseclient.Column(
            name=release, columnType="INTEGER", defaultValue=0
        )
        new_column = syn.store(syn_col)
        schema.addColumn(new_column)
        # no need to return schema variable because it isn't used
        syn.store(schema)
    # Columns of samples in release
    samples_per_releasedf = extract.get_syntabledf(
        syn=syn,
        query_string=f'SELECT SAMPLE_ID, "{release}" FROM {samples_in_release_synid}',
    )
    new_samples = clinicaldf[["SAMPLE_ID"]][
        ~clinicaldf.SAMPLE_ID.isin(samples_per_releasedf.SAMPLE_ID)
    ]

    new_samples[release] = 1
    old_samples = clinicaldf[["SAMPLE_ID"]][
        clinicaldf.SAMPLE_ID.isin(samples_per_releasedf.SAMPLE_ID)
    ]

    old_samples[release] = 1
    samples_in_releasedf = new_samples.append(old_samples)
    load._update_table(
        syn,
        samples_per_releasedf,
        samples_in_releasedf,
        samples_in_release_synid,
        ["SAMPLE_ID"],
    )


def update_cumulative_sample_table(
    syn, file_mapping, release, cumulative_sample_count_synid
):
    """
    Consortium release sample count table update function
    This gets the cumulative sample count of each file type in each release

    Args:
        syn: synapse object
        file_mapping: file mapping generated from file mapping function
        release:  GENIE release number (ie. 5.3-consortium)
        cumulative_sample_count_synid: Synapse Id of
            'Cumulative sample count' Table
    """
    sample_count_per_rounddf = extract.get_syntabledf(
        syn=syn,
        query_string=f"SELECT * FROM {cumulative_sample_count_synid} where Release = '{release}'",
    )
    clinical_ent = syn.get(file_mapping["sample"], followLink=True)
    clinicaldf = pd.read_csv(clinical_ent.path, sep="\t", comment="#")
    clinicaldf.columns = [i.upper() for i in clinicaldf.columns]
    if clinicaldf.get("CENTER") is None:
        clinicaldf["CENTER"] = [sample.split("-")[1] for sample in clinicaldf.SAMPLE_ID]
    clinical_counts = clinicaldf["CENTER"].value_counts()
    clinical_counts["Total"] = sum(clinical_counts)
    clinical_counts.name = "Clinical"

    sv_ent = syn.get(file_mapping["sv"], followLink=True)
    sv_df = pd.read_csv(sv_ent.path, sep="\t", comment="#")
    sv_df.columns = [col.upper() for col in sv_df.columns]
    sv_counts = sv_df["CENTER"][~sv_df["SAMPLE_ID"].duplicated()].value_counts()
    sv_counts["Total"] = sum(sv_counts)

    cna_ent = syn.get(file_mapping["cna"], followLink=True)
    cnadf = pd.read_csv(cna_ent.path, sep="\t", comment="#")
    cna_counts = pd.Series([i.split("-")[1] for i in cnadf.columns[1:]]).value_counts()
    cna_counts["Total"] = sum(cna_counts)

    seg_ent = syn.get(file_mapping["seg"], followLink=True)
    segdf = pd.read_csv(seg_ent.path, sep="\t", comment="#")
    segdf.columns = [i.upper() for i in segdf.columns]

    segdf["CENTER"] = [i.split("-")[1] for i in segdf["ID"]]
    seg_counts = segdf["CENTER"][~segdf["ID"].duplicated()].value_counts()
    seg_counts["Total"] = sum(seg_counts)

    total_counts = pd.DataFrame(clinical_counts)
    total_counts["Fusions"] = sv_counts
    total_counts["CNV"] = cna_counts
    total_counts["Mutation"] = clinical_counts
    total_counts["SEG"] = seg_counts
    total_counts = total_counts.fillna(0)
    total_counts = total_counts.applymap(int)
    total_counts["Center"] = total_counts.index
    total_counts["Release"] = release
    load._update_table(
        syn,
        sample_count_per_rounddf,
        total_counts,
        cumulative_sample_count_synid,
        ["Center", "Release"],
        to_delete=True,
    )


def update_release_numbers(syn, database_mappingdf, release=None):
    """
    Updates all release dashboard numbers or specific release number

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database
        release: GENIE release (ie. 5.3-consortium).  Defaults to None
    """
    # Update release table with current release or all releases
    samples_in_release_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "samplesInRelease"
    ].values[0]
    cumulative_sample_count_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "cumulativeSampleCount"
    ].values[0]

    release_folder_fileview_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "releaseFolder"
    ].values[0]
    # Add this query so that the fileview is indexed to include the
    # new release folder
    syn.tableQuery(f"select * from {release_folder_fileview_synid} limit 1")
    query_str = (
        f"select id,name from {release_folder_fileview_synid} where "
        "name not like 'Release%' and name <> 'case_lists' and "
        "name not like '%.0.%'"
    )
    release_folderdf = extract.get_syntabledf(syn=syn, query_string=query_str)

    for rel_synid, rel_name in zip(release_folderdf.id, release_folderdf.name):
        file_mapping = extract.get_file_mapping(syn, rel_synid)
        # If release is specified, only process on that,
        # otherwise process for all
        if release is None or release == rel_name:
            update_samples_in_release_table(
                syn, file_mapping, rel_name, samples_in_release_synid
            )
            update_cumulative_sample_table(
                syn, file_mapping, rel_name, cumulative_sample_count_synid
            )
        else:
            pass


def update_database_numbers(syn, database_mappingdf):
    """
    Updates database cumulative numbers (Only called when not staging)

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database
    """
    cumulative_sample_count_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "cumulativeSampleCount"
    ].values[0]
    # Database
    database_countdf = extract.get_syntabledf(
        syn=syn,
        query_string=f"SELECT * FROM {cumulative_sample_count_synid} where Release = 'Database'",
    )
    clinicaldf = extract.get_syntabledf(
        syn=syn, query_string="select CENTER from syn7517674"
    )
    clinincal_counts = clinicaldf["CENTER"].value_counts()
    clinincal_counts["Total"] = sum(clinincal_counts)
    clinincal_counts.name = "Clinical"
    sv_df = extract.get_syntabledf(syn=syn, query_string="select * from syn30891574")
    sv_counts = sv_df["CENTER"][~sv_df["SAMPLE_ID"].duplicated()].value_counts()
    sv_counts["Total"] = sum(sv_counts)

    center_flat_files = syn.getChildren("syn12278118")
    cna_file_paths = [
        syn.get(file["id"]).path
        for file in center_flat_files
        if file["name"].startswith("data_CNA")
    ]
    cna_numbers = {}
    for cna_file in cna_file_paths:
        center = os.path.basename(cna_file).replace(".txt", "").split("_")[2]
        with open(cna_file, "r") as cna:
            header = cna.readline()
            samples = header.split("\t")
            # Minus one because of Hugo_Symbol
            cna_numbers[center] = len(samples) - 1
    cna_counts = pd.Series(cna_numbers)
    cna_counts["Total"] = sum(cna_counts)
    segdf = extract.get_syntabledf(syn=syn, query_string="select * from syn7893341")
    seg_counts = segdf["CENTER"][~segdf["ID"].duplicated()].value_counts()
    seg_counts["Total"] = sum(seg_counts)

    db_counts = pd.DataFrame(clinincal_counts)
    db_counts["Fusions"] = sv_counts
    db_counts["CNV"] = cna_counts
    db_counts["Mutation"] = clinincal_counts
    db_counts["SEG"] = seg_counts
    db_counts = db_counts.fillna(0)
    db_counts = db_counts.applymap(int)
    db_counts["Center"] = db_counts.index
    db_counts["Release"] = "Database"
    load._update_table(
        syn,
        database_countdf,
        db_counts,
        cumulative_sample_count_synid,
        ["Center", "Release"],
    )
    today = datetime.date.today()
    if today.month in [1, 4, 8, 12]:
        db_count_tracker = db_counts[["Clinical", "Center", "Release"]]
        db_count_tracker.rename(
            columns={"Clinical": "sample_count", "Center": "center", "Release": "date"},
            inplace=True,
        )
        db_count_tracker["date"] = today.strftime("%b-%Y")
        # Hard coded syn id
        syn.store(synapseclient.Table("syn18404852", db_count_tracker))


def update_oncotree_code_tables(syn, database_mappingdf):
    """
    Updates database statistics of oncotree codes
    and primary onocotree codes

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database
    """
    oncotree_distribution_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "oncotree"
    ].values[0]
    clinicaldf = extract.get_syntabledf(
        syn=syn, query_string="select * from syn7517674"
    )

    # DISTRIBUTION OF ONCOTREE CODE TABLE UPDATE
    oncotree_code_distributiondf = pd.DataFrame(
        columns=set(clinicaldf["CENTER"]), index=set(clinicaldf["ONCOTREE_CODE"])
    )
    for center in oncotree_code_distributiondf.columns:
        onc_counts = clinicaldf["ONCOTREE_CODE"][
            clinicaldf["CENTER"] == center
        ].value_counts()
        oncotree_code_distributiondf[center] = onc_counts
    oncotree_code_distributiondf = oncotree_code_distributiondf.fillna(0)
    oncotree_code_distributiondf = oncotree_code_distributiondf.applymap(int)
    oncotree_code_distributiondf["Total"] = oncotree_code_distributiondf.apply(
        sum, axis=1
    )
    oncotree_code_distributiondf["Oncotree_Code"] = oncotree_code_distributiondf.index

    center_string = ",".join(clinicaldf["CENTER"].unique())
    oncotree_distribution_dbdf = extract.get_syntabledf(
        syn=syn,
        query_string=f"SELECT Oncotree_Code,{center_string},Total  FROM {oncotree_distribution_synid}",
    )
    load._update_table(
        syn,
        oncotree_distribution_dbdf,
        oncotree_code_distributiondf,
        oncotree_distribution_synid,
        ["Oncotree_Code"],
        to_delete=True,
    )

    # DISTRIBUTION OF PRIMARY CODE TABLE UPDATE
    oncotree_link_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "oncotreeLink"
    ].values[0]
    primary_code_synId = database_mappingdf["Id"][
        database_mappingdf["Database"] == "primaryCode"
    ].values[0]

    # Can also use most up to date oncotree code,
    # because these tables are updated from the database
    oncotree_link_ent = syn.get(oncotree_link_synid)
    oncotree_link = oncotree_link_ent.externalURL
    oncotree_mapping = process_functions.get_oncotree_code_mappings(oncotree_link)

    clinicaldf["PRIMARY_CODES"] = [
        oncotree_mapping[i.upper()]["ONCOTREE_PRIMARY_NODE"]
        if i.upper() in oncotree_mapping.keys()
        else "DEPRECATED_CODE"
        for i in clinicaldf.ONCOTREE_CODE
    ]

    # ### DISTRIBUTION OF PRIMARY ONCOTREE CODE TABLE UPDATE
    primary_code_distributiondf = pd.DataFrame(
        columns=set(clinicaldf["CENTER"]), index=set(clinicaldf["PRIMARY_CODES"])
    )

    for center in primary_code_distributiondf.columns:
        onc_counts = clinicaldf["PRIMARY_CODES"][
            clinicaldf["CENTER"] == center
        ].value_counts()
        primary_code_distributiondf[center] = onc_counts
    primary_code_distributiondf = primary_code_distributiondf.fillna(0)
    primary_code_distributiondf = primary_code_distributiondf.applymap(int)
    primary_code_distributiondf["Total"] = primary_code_distributiondf.apply(
        sum, axis=1
    )
    primary_code_distributiondf["Oncotree_Code"] = primary_code_distributiondf.index
    primary_code_dist_dbdf = extract.get_syntabledf(
        syn=syn,
        query_string=f"SELECT Oncotree_Code,{center_string},Total  FROM {primary_code_synId}",
    )
    load._update_table(
        syn,
        primary_code_dist_dbdf,
        primary_code_distributiondf,
        primary_code_synId,
        ["Oncotree_Code"],
        to_delete=True,
    )


def update_sample_difference_table(syn, database_mappingdf):
    """
    Updates sample difference table between
    consortium releases

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database
    """
    cumulative_sample_count_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "cumulativeSampleCount"
    ].values[0]

    sample_diff_count_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "sampleDiffCount"
    ].values[0]

    # UPDATE DIFF TABLE
    sample_count_per_rounddf = extract.get_syntabledf(
        syn=syn,
        query_string=f"SELECT * FROM {cumulative_sample_count_synid} where Center <> 'Total' and Release <> 'Database'",
    )
    releases = list(sample_count_per_rounddf["Release"].unique())
    # sort the releases and remove public releases
    releases.sort()
    consortium_releases = [
        release
        for release in releases
        if "public" not in release and ".0." not in release
    ]

    diff_between_releasesdf = sample_count_per_rounddf[
        sample_count_per_rounddf["Release"] == consortium_releases[0]
    ]

    for index, release_name in enumerate(consortium_releases[1:]):
        prior_release = sample_count_per_rounddf[
            sample_count_per_rounddf["Release"] == consortium_releases[index]
        ]

        current_release = sample_count_per_rounddf[
            sample_count_per_rounddf["Release"] == release_name
        ]

        prior_release.index = prior_release["Center"]
        current_release.index = current_release["Center"]

        del prior_release["Center"]
        del prior_release["Release"]
        del current_release["Center"]
        del current_release["Release"]
        # Append new rows of centers that are new and
        # just added to the releases
        new_centers = current_release.index[
            ~current_release.index.isin(prior_release.index)
        ]

        if not new_centers.empty:
            prior_release = pd.concat([prior_release, pd.DataFrame(index=new_centers)])
            prior_release = prior_release.fillna(0)
        difference = current_release - prior_release
        difference["Center"] = difference.index
        difference["Release"] = release_name
        diff_between_releasesdf = pd.concat([diff_between_releasesdf, difference])
    difftable_dbdf = extract.get_syntabledf(
        syn=syn, query_string=f"SELECT * FROM {sample_diff_count_synid}"
    )
    difftable_dbdf = difftable_dbdf.fillna(0)
    new_values = (
        diff_between_releasesdf[["Clinical", "Mutation", "CNV", "SEG", "Fusions"]]
        .fillna(0)
        .applymap(int)
    )

    diff_between_releasesdf[
        ["Clinical", "Mutation", "CNV", "SEG", "Fusions"]
    ] = new_values

    load._update_table(
        syn,
        difftable_dbdf,
        diff_between_releasesdf,
        sample_diff_count_synid,
        ["Center", "Release"],
        to_delete=True,
    )


def update_data_completeness_table(syn, database_mappingdf):
    """
    Updates the data completeness of the database

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database
    """
    data_completion_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "dataCompletion"
    ].values[0]

    sampledf = extract.get_syntabledf(syn=syn, query_string="select * from syn7517674")
    patientdf = extract.get_syntabledf(syn=syn, query_string="select * from syn7517669")
    data_completenessdf = pd.DataFrame()
    center_infos = sampledf.CENTER.drop_duplicates().apply(
        lambda center: get_center_data_completion(center, sampledf)
    )
    for center_info in center_infos:
        data_completenessdf = pd.concat([data_completenessdf, center_info])

    center_infos = patientdf.CENTER.drop_duplicates().apply(
        lambda center: get_center_data_completion(center, patientdf)
    )
    for center_info in center_infos:
        data_completenessdf = pd.concat([data_completenessdf, center_info])
    data_completeness_dbdf = extract.get_syntabledf(
        syn=syn, query_string=f"select * from {data_completion_synid}"
    )
    data_completenessdf.columns = data_completeness_dbdf.columns
    load._update_table(
        syn,
        data_completeness_dbdf,
        data_completenessdf,
        data_completion_synid,
        ["FIELD", "CENTER"],
        to_delete=True,
    )


def update_wiki(syn, database_mappingdf):
    """
    Updates the GENIE project dashboard wiki timestamp

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database

    """
    # Updates to query and date dashboard was updated
    cumulative_sample_count_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "cumulativeSampleCount"
    ].values[0]

    primary_code_synId = database_mappingdf["Id"][
        database_mappingdf["Database"] == "primaryCode"
    ].values[0]
    centersdf = extract.get_syntabledf(
        syn=syn, query_string="select distinct(CENTER) as CENTER from syn7517674"
    )
    now = datetime.datetime.now()
    markdown = [
        "_Updated {month}/{day}/{year}_\n\n".format(
            month=now.month, day=now.day, year=now.year
        ),
        "##Count of Clinical Samples\n",
        "${synapsetable?query=SELECT Center%2C Clinical%2C Release FROM "
        + cumulative_sample_count_synid
        + "}\n\n",
        "\n\n##Primary Oncotree Codes\n\n",
        "${synapsetable?query=SELECT Oncotree%5FCode%2C "
        + "%2C ".join(centersdf["CENTER"].unique())
        + "%2C Total FROM "
        + primary_code_synId
        + " ORDER BY Total DESC&limit=15}\n\n",
    ]

    wikipage = syn.getWiki("syn3380222", 235803)
    wikipage.markdown = "".join(markdown)
    syn.store(wikipage)


def string_to_unix_epoch_time_milliseconds(string_time):
    """
    Takes dates in this format: 2018-10-25T20:16:07.959Z
    and turns it into unix epoch time in milliseconds

    Args:
        string_time: string in this format: 2018-10-25T20:16:07.959Z

    Returns:
        unix epoch time in milliseconds
    """
    datetime_obj = datetime.datetime.strptime(
        string_time.split(".")[0], "%Y-%m-%dT%H:%M:%S"
    )
    return to_unix_epoch_time(datetime_obj)


def update_data_release_file_table(syn, database_mappingdf):
    """
    Updates data release file table

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database
    """
    release_folder_fileview_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "releaseFolder"
    ].values[0]
    # Add this query so that the fileview is indexed to include the
    # new release folder
    # syn.tableQuery(f"select * from {release_folder_fileview_synid} limit 1")
    query_str = (
        f"select id,name from {release_folder_fileview_synid} where "
        "name not like 'Release%' and name <> 'case_lists' "
        "and name not like '0.%'"
    )
    release_folderdf = extract.get_syntabledf(syn=syn, query_string=query_str)

    data_release_table_synid = "syn16804261"
    data_release_tabledf = extract.get_syntabledf(
        syn=syn, query_string=f"select * from {data_release_table_synid}"
    )

    not_in_release_tabledf = release_folderdf[
        ~release_folderdf.name.isin(data_release_tabledf.release)
    ]

    for synid, name in zip(not_in_release_tabledf.id, not_in_release_tabledf.name):
        release_files = syn.getChildren(synid)

        append_rows = [
            [
                release_file["name"],
                release_file["id"],
                name,
                string_to_unix_epoch_time_milliseconds(release_file["modifiedOn"]),
                synid,
            ]
            for release_file in release_files
            if release_file["name"] != "case_lists"
        ]

        syn.store(synapseclient.Table(data_release_table_synid, append_rows))


def check_column_decreases(currentdf, olderdf):
    """
    Checks entity decreases

    Args:
        current_ent: Current entity dataframe
        old_ent: Older entity dataframe

    Returns:
        Differences in values
    """
    diff_map = dict()
    for col in currentdf:
        new_counts = currentdf[col].value_counts()
        if olderdf.get(col) is not None:
            old_counts = olderdf[col].value_counts()
            # Make sure any values that exist in the new get added
            # to the old to show the decrease
            new_keys = pd.Series(
                index=new_counts.keys()[~new_counts.keys().isin(old_counts.keys())]
            )
            old_counts = old_counts.add(new_keys, fill_value=0)
            old_counts.fillna(0, inplace=True)
            # Make sure any values that don't exist in the old get added
            # to show the decrease
            new_keys = pd.Series(
                index=old_counts.keys()[~old_counts.keys().isin(new_counts.keys())]
            )
            new_counts = new_counts.add(new_keys, fill_value=0)
            new_counts.fillna(0, inplace=True)
            if any(new_counts - old_counts < 0):
                logger.info("\tDECREASE IN COLUMN: %s" % col)
                # diff = new_counts[new_counts - old_counts < 0]
                diffs = new_counts - old_counts
                diffstext = diffs[diffs < 0].to_csv().replace("\n", "; ")
                logger.info("\t" + diffstext)
                diff_map[col] = True
            else:
                diff_map[col] = False
    return diff_map


def print_clinical_values_difference_table(syn, database_mappingdf):
    """
    Checks for a decrease in values in the clinical file
    from last consortium release to most recent consortium release

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database
    """
    release_folder_fileview_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "releaseFolder"
    ].values[0]

    clinical_key_decrease_synid = database_mappingdf["Id"][
        database_mappingdf["Database"] == "clinicalKeyDecrease"
    ].values[0]

    query_str = (
        f"select id,name from {release_folder_fileview_synid} where "
        "name not like 'Release%' and name <> 'case_lists' "
        "and name not like '%.0.%' and name not like '%-public' "
        "and name <> 'potential_artifacts'"
    )
    release_folderdf = extract.get_syntabledf(syn=syn, query_string=query_str)
    # Set release number as a numerical value since string "10" < "9"
    # Also can't set by created on date, because sometimes
    # there are patch releases
    release_folderdf["num_release"] = [
        float(name.replace(".0", "").replace("-consortium", ""))
        for name in release_folderdf["name"]
    ]
    release_folderdf.sort_values("num_release", ascending=False, inplace=True)
    current_release = release_folderdf["id"][0]
    older_release = release_folderdf["id"][1]

    current_release_files = syn.getChildren(current_release)
    current_clinical_synids = {
        file["name"]: file["id"]
        for file in current_release_files
        if file["name"] in ["data_clinical_sample.txt", "data_clinical_patient.txt"]
    }

    older_release_files = syn.getChildren(older_release)

    older_clinical_synids = {
        file["name"]: file["id"]
        for file in older_release_files
        if file["name"] in ["data_clinical_sample.txt", "data_clinical_patient.txt"]
    }

    current_sample_ent = syn.get(
        current_clinical_synids["data_clinical_sample.txt"], followLink=True
    )

    older_sample_ent = syn.get(
        older_clinical_synids["data_clinical_sample.txt"], followLink=True
    )
    current_sampledf = pd.read_csv(current_sample_ent.path, sep="\t", comment="#")

    current_sampledf["CENTER"] = [
        patient.split("-")[1] for patient in current_sampledf["PATIENT_ID"]
    ]

    older_sampledf = pd.read_csv(older_sample_ent.path, sep="\t", comment="#")
    older_sampledf["CENTER"] = [
        patient.split("-")[1] for patient in older_sampledf["PATIENT_ID"]
    ]
    # Rather than take the CENTER, must take the SAMPLE_ID to compare
    current_sampledf = current_sampledf[
        current_sampledf["SAMPLE_ID"].isin(older_sampledf["SAMPLE_ID"].unique())
    ]

    logger.info("SAMPLE CLINICAL VALUE DECREASES")
    center_decrease_mapping = dict()
    for center in older_sampledf["CENTER"].unique():
        current_center_sampledf = current_sampledf[current_sampledf["CENTER"] == center]

        older_center_sampledf = older_sampledf[older_sampledf["CENTER"] == center]

        logger.info(center)

        decrease_map = check_column_decreases(
            current_center_sampledf, older_center_sampledf
        )
        center_decrease_mapping[center] = decrease_map

    current_patient_ent = syn.get(
        current_clinical_synids["data_clinical_patient.txt"], followLink=True
    )

    older_patient_ent = syn.get(
        older_clinical_synids["data_clinical_patient.txt"], followLink=True
    )

    current_patientdf = pd.read_csv(current_patient_ent.path, sep="\t", comment="#")

    older_patientdf = pd.read_csv(older_patient_ent.path, sep="\t", comment="#")
    # Rather than take the CENTER, must take the PATIENT_ID to compare
    current_patientdf = current_patientdf[
        current_patientdf["PATIENT_ID"].isin(older_patientdf["PATIENT_ID"].unique())
    ]

    logger.info("PATIENT CLINICAL VALUE DECREASES")
    for center in older_patientdf["CENTER"].unique():
        current_center_patientdf = current_patientdf[
            current_patientdf["CENTER"] == center
        ]

        older_center_patientdf = older_patientdf[older_patientdf["CENTER"] == center]

        logger.info(center)
        patient_decrease_map = check_column_decreases(
            current_center_patientdf, older_center_patientdf
        )

        center_decrease_mapping[center].update(patient_decrease_map)

    center_decrease_mapping = pd.DataFrame(center_decrease_mapping)
    center_decrease_mapping = center_decrease_mapping.transpose()
    center_decrease_mapping["CENTER"] = center_decrease_mapping.index

    clinical_key_decreasedbdf = extract.get_syntabledf(
        syn=syn, query_string=f"select * from {clinical_key_decrease_synid}"
    )
    load._update_table(
        syn,
        clinical_key_decreasedbdf,
        center_decrease_mapping,
        clinical_key_decrease_synid,
        ["CENTER"],
        to_delete=True,
    )


def run_dashboard(syn, database_mappingdf, release, staging=False, public=False):
    """
    Runs the dashboard scripts

    Args:
        syn: synapse object
        database_mappingdf: mapping between synapse ids and database
        release: GENIE release (ie. 5.3-consortium)

    """
    update_release_numbers(syn, database_mappingdf, release=release)

    if not staging:
        update_data_release_file_table(syn, database_mappingdf)
        if not public:
            print_clinical_values_difference_table(syn, database_mappingdf)
            update_sample_difference_table(syn, database_mappingdf)
            update_data_completeness_table(syn, database_mappingdf)
            update_database_numbers(syn, database_mappingdf)
            update_oncotree_code_tables(syn, database_mappingdf)
            update_wiki(syn, database_mappingdf)


def main():
    parser = argparse.ArgumentParser(description="Update dashboard tables")

    parser.add_argument(
        "--release", help="GENIE release number (ie. 5.3-consortium)", default=None
    )

    parser.add_argument(
        "--staging", action="store_true", help="Using staging directory files"
    )

    parser.add_argument("--debug", action="store_true", help="Synapse debugging flag")

    parser.add_argument(
        "--public", action="store_true", help="Set true if releasing public release"
    )

    args = parser.parse_args()
    syn = process_functions.synapse_login(debug=args.debug)
    if args.staging:
        # Database to Synapse Id mapping Table
        # TODO: use project ids instead of table ids
        database_mapping_synid = "syn12094210"
    else:
        database_mapping_synid = "syn10967259"

    # TODO: get genie config here... that would be a lot easier
    # extract.get_genie_config(syn=syn, project_id=)
    database_mapping = syn.tableQuery("select * from %s" % database_mapping_synid)
    database_mappingdf = database_mapping.asDataFrame()

    run_dashboard(
        syn, database_mappingdf, args.release, staging=args.staging, public=args.public
    )


if __name__ == "__main__":
    main()
