from unittest.mock import Mock, patch
import uuid

import pandas as pd
import pytest
import synapseclient

from genie import process_functions

DATABASE_DF = pd.DataFrame(
    {
        "UNIQUE_KEY": ["test1", "test2", "test3"],
        "test": ["test1", "test2", "test3"],
        "foo": [1, 2, 3],
        "baz": [float("nan"), float("nan"), float("nan")],
    }
)
DATABASE_DF.index = ["1_3", "2_3", "3_5"]
ENTITY = synapseclient.Project("foo", annotations={"dbMapping": ["syn1234"]})
ONCOTREE_ENT = "syn222"


@pytest.mark.parametrize(
    "input_str,output",
    [
        ("1.0\t", "1\t"),
        ("1.0\n", "1\n"),
        ("1.5\t", "1.5\t"),
        ("1\t", "1\t"),
        ("0\t", "0\t"),
        ("'a'\t'b'\n1.0\t2.0\n", "'a'\t'b'\n1\t2\n"),
    ],
)
def test_removeStringFloat(input_str, output):
    """Remove string float - will always assume that there is a \n
    at the end.  This is because if a value was 2.01, we dont want to
    remove the .0 from this."""
    assert process_functions.removeStringFloat(input_str) == output


def test_valid__check_valid_df():
    process_functions._check_valid_df(DATABASE_DF, "test")


def test_invalid__check_valid_df():
    with pytest.raises(ValueError, match="Must pass in pandas dataframe"):
        process_functions._check_valid_df("foo", "test")
    with pytest.raises(ValueError, match="'error' column must exist in dataframe"):
        process_functions._check_valid_df(DATABASE_DF, "error")


def test__get_left_diff_df():
    new_datadf = pd.DataFrame(
        {
            "UNIQUE_KEY": ["test1", "test2", "test3", "test4"],
            "test": ["test1", "test2", "test3", "test4"],
            "foo": [1, 2, 3, 4],
            "baz": [float("nan"), float("nan"), float("nan"), 3.2],
        }
    )
    get_diff = process_functions._get_left_diff_df(
        new_datadf, DATABASE_DF, "UNIQUE_KEY"
    )
    expecteddf = new_datadf.loc[[3]]
    assert get_diff.equals(expecteddf[get_diff.columns])


def test_norows_get_left_diff_df():
    append_rows = process_functions._get_left_diff_df(
        DATABASE_DF, DATABASE_DF, "UNIQUE_KEY"
    )
    assert append_rows.empty


def test_first_validation_get_left_diff_df():
    """
    This checks to make sure that validation is called
    - In a situation where someone comments out the validation
    line, this will cause an error
    """
    with pytest.raises(ValueError, match="'FOO' column must exist in dataframe"):
        process_functions._get_left_diff_df(DATABASE_DF, DATABASE_DF, "FOO")


def test_second_validation_get_left_diff_df():
    """
    This checks to make sure that validation is called
    - In a situation where someone comments out the validation
    line, this will cause an error
    """
    testing = DATABASE_DF.copy()
    testing["FOO"] = float("nan")
    with pytest.raises(ValueError, match="'FOO' column must exist in dataframe"):
        process_functions._get_left_diff_df(testing, DATABASE_DF, "FOO")


def test_first_validation_get_left_union_df():
    """
    This checks to make sure that validation is called
    - In a situation where someone comments out the 1st validation
    line, this will cause an error
    """
    with pytest.raises(ValueError, match="'FOO' column must exist in dataframe"):
        process_functions._get_left_union_df(DATABASE_DF, DATABASE_DF, "FOO")


def test_second_validation_get_left_union_df():
    """
    This checks to make sure that validation is called
    - In a situation where someone comments out the 2nd validation
    line, this will cause an error
    """
    testing = DATABASE_DF.copy()
    testing["FOO"] = float("nan")
    with pytest.raises(ValueError, match="'FOO' column must exist in dataframe"):
        process_functions._get_left_union_df(testing, DATABASE_DF, "FOO")


def test_append__append_rows():
    new_datadf = pd.DataFrame(
        {
            "UNIQUE_KEY": ["test1", "test2", "test3", "test4"],
            "test": ["test1", "test2", "test3", "test4"],
            "foo": [1, 2, 3, 4],
            "baz": [float("nan"), float("nan"), float("nan"), 3.2],
        }
    )
    expecteddf = pd.DataFrame({"test": ["test4"], "foo": [4], "baz": [3.2]})
    append_rows = process_functions._append_rows(new_datadf, DATABASE_DF, "UNIQUE_KEY")
    append_rows.fillna("", inplace=True)
    expecteddf.fillna("", inplace=True)
    assert append_rows.equals(expecteddf[append_rows.columns])


def test___create_update_rowsdf():
    differentrows = [True, True, False]
    database = pd.DataFrame(
        {
            "test": ["test", "test2", "test3"],
            "foo": [1, 3, 3],
            "baz": [float("nan"), 5, float("nan")],
        },
        index=["test1", "test5", "test4"],
    )
    new_datadf = pd.DataFrame(
        {
            "test": ["test1", "test4", "test3"],
            "foo": [2, 3, 3],
            "baz": [3, 5, float("nan")],
        },
        index=["test1", "test5", "test4"],
    )

    to_update_rowsdf = process_functions._create_update_rowsdf(
        database, new_datadf, DATABASE_DF.index, differentrows
    )
    expecteddf = pd.DataFrame(
        {
            "test": ["test1", "test4"],
            "foo": [2, 3],
            "baz": [3.0, 5.0],
            "ROW_ID": ["1", "2"],
            "ROW_VERSION": ["3", "3"],
        }
    )
    assert to_update_rowsdf.equals(expecteddf[to_update_rowsdf.columns])


def test_none__create_update_rowsdf():
    differentrows = [False, False, False]
    database = pd.DataFrame(
        {
            "test": ["test", "test2", "test3"],
            "foo": [1, 3, 3],
            "baz": [float("nan"), 5, float("nan")],
        },
        index=["test1", "test5", "test4"],
    )
    new_datadf = pd.DataFrame(
        {
            "test": ["test1", "test4", "test3"],
            "foo": [2, 3, 3],
            "baz": [3, 5, float("nan")],
        },
        index=["test1", "test5", "test4"],
    )

    to_update_rowsdf = process_functions._create_update_rowsdf(
        database, new_datadf, DATABASE_DF.index, differentrows
    )
    assert to_update_rowsdf.empty


def test___get_left_union_df():
    new_datadf = pd.DataFrame(
        {
            "UNIQUE_KEY": ["test1", "test5", "test4"],
            "test": ["test", "test2", "test3"],
            "foo": [1, 3, 3],
            "baz": [float("nan"), 5, float("nan")],
        }
    )
    left_union = process_functions._get_left_union_df(
        new_datadf, DATABASE_DF, "UNIQUE_KEY"
    )
    expecteddf = pd.DataFrame(
        {"UNIQUE_KEY": ["test1"], "test": ["test"], "foo": [1], "baz": [float("nan")]}
    )
    assert left_union.equals(expecteddf[left_union.columns])


def test_none__get_left_union_df():
    new_datadf = pd.DataFrame(
        {
            "UNIQUE_KEY": ["test7", "test5", "test4"],
            "test": ["test", "test2", "test3"],
            "foo": [1, 3, 3],
            "baz": [float("nan"), 5, float("nan")],
        }
    )
    left_union = process_functions._get_left_union_df(
        new_datadf, DATABASE_DF, "UNIQUE_KEY"
    )
    assert left_union.empty


def test_update__update_rows():
    """
    Tests index comparison for updating rows
    """
    new_datadf = pd.DataFrame(
        {
            "UNIQUE_KEY": ["test1", "test2", "test3"],
            "test": ["test", "test2", "test3"],
            "foo": [1, 3, 3],
            "baz": [float("nan"), 5, float("nan")],
        }
    )

    expecteddf = pd.DataFrame(
        {
            "test": ["test", "test2"],
            "foo": [1, 3],
            "baz": ["", 5],
            "ROW_ID": ["1", "2"],
            "ROW_VERSION": ["3", "3"],
        }
    )
    update_rows = process_functions._update_rows(new_datadf, DATABASE_DF, "UNIQUE_KEY")
    assert update_rows.equals(expecteddf[update_rows.columns])


def test_maintaintype__update_rows():
    """
    Test pandas behavior.  Integer -> Float if NA exists
    """
    new_datadf = pd.DataFrame(
        {
            "UNIQUE_KEY": ["test1", "test2", "test3"],
            "test": ["test1", "test2", "test3"],
            "foo": [1, 3, 3],
            "baz": [float("nan"), 5, float("nan")],
        }
    )
    # Test that the datatype passed into from new_datadf gets preserved
    expecteddf = pd.DataFrame(
        {
            "test": ["test2"],
            "foo": [3],
            "baz": [5],
            "ROW_ID": ["2"],
            "ROW_VERSION": ["3"],
        }
    )
    expecteddf = expecteddf.astype({"baz": object})
    update_rows = process_functions._update_rows(new_datadf, DATABASE_DF, "UNIQUE_KEY")
    assert update_rows.equals(expecteddf[update_rows.columns])


def test_noupdate__update_rows():
    """
    Tests the index comparison to get no updates
    """
    new_datadf = pd.DataFrame(
        {"UNIQUE_KEY": ["test4"], "test": ["test"], "foo": [1], "baz": [float("nan")]}
    )
    update_rows = process_functions._update_rows(new_datadf, DATABASE_DF, "UNIQUE_KEY")
    assert update_rows.empty


def test_delete__delete_rows():
    new_datadf = pd.DataFrame(
        {"UNIQUE_KEY": ["test1"], "test": ["test1"], "foo": [1], "baz": [float("nan")]}
    )
    expecteddf = pd.DataFrame({0: ["2", "3"], 1: ["3", "5"]})
    delete_rows = process_functions._delete_rows(new_datadf, DATABASE_DF, "UNIQUE_KEY")
    assert delete_rows.equals(expecteddf)


def test_norows__delete_rows():
    delete_rows = process_functions._delete_rows(DATABASE_DF, DATABASE_DF, "UNIQUE_KEY")
    assert delete_rows.empty


def test__create_schema(syn):
    """Tests calling of create schema"""
    table_name = str(uuid.uuid1())
    parentid = str(uuid.uuid1())
    columns = [str(uuid.uuid1())]
    annotations = {"foo": "bar"}

    schema = synapseclient.Schema(
        table_name, columns=columns, parent=parentid, annotations=annotations
    )
    with patch.object(syn, "store", return_value=schema) as patch_syn_store:
        new_schema = process_functions._create_schema(
            syn, table_name, parentid, columns=columns, annotations=annotations
        )
        patch_syn_store.assert_called_once_with(schema)
        assert new_schema == schema


def test__update_database_mapping(syn):
    """Tests updates database mapping"""
    fileformat = str(uuid.uuid1())
    database_mappingdf = pd.DataFrame(
        {"Database": [fileformat, "foo"], "Id": ["11111", "bar"]}
    )
    database_mapping_synid = str(uuid.uuid1())
    new_tableid = str(uuid.uuid1())
    expected_mapdf = pd.DataFrame(
        {"Database": [fileformat, "foo"], "Id": [new_tableid, "bar"]}
    )
    with patch.object(syn, "store") as patch_syn_store:
        newdb = process_functions._update_database_mapping(
            syn, database_mappingdf, database_mapping_synid, fileformat, new_tableid
        )
        assert newdb.equals(expected_mapdf)
        patch_syn_store.assert_called_once()


def test_noname__move_entity(syn):
    """Tests not changing entity name"""
    ent = synapseclient.Entity(name="foo", parentId="syn2222")
    new_parent = "syn1234"
    with patch.object(syn, "store") as patch_syn_store:
        process_functions._move_entity(syn, ent, new_parent)
        ent.parentId = new_parent
        patch_syn_store.assert_called_once_with(ent)


def test_name__move_entity(syn):
    """Tests entity name is updated"""
    ent = synapseclient.Entity(name="foo", parentId="syn2222")
    new_parent = "syn1234"
    new_name = "updated name"
    with patch.object(syn, "store") as patch_syn_store:
        process_functions._move_entity(syn, ent, new_parent, new_name)
        ent.parentId = new_parent
        ent.name = new_name
        patch_syn_store.assert_called_once_with(ent)


def test_create_new_fileformat_table(syn):
    fileformat = str(uuid.uuid1())
    db_synid = "syn1111111"
    database_mappingdf = pd.DataFrame(
        {"Database": [fileformat, "foo"], "Id": [db_synid, "bar"]}
    )
    db_mapping_info = {"synid": "syn666", "df": database_mappingdf}
    table_ent = synapseclient.Entity(
        parentId="syn123", name="foo", primaryKey=["annot"], id="syn12345"
    )
    project_id = "syn234"
    archived_project_id = "syn23333"
    new_table_name = str(uuid.uuid1())

    new_table_ent = synapseclient.Entity(
        parentId="syn123323", name="foofoo", id="syn23231"
    )
    update_return = Mock()
    move_entity_return = Mock()
    with patch.object(
        process_functions, "get_dbmapping", return_value=db_mapping_info
    ) as patch_getdb, patch.object(
        syn, "get", return_value=table_ent
    ) as patch_syn_get, patch.object(
        syn, "getTableColumns", return_value=["foo", "ddooo"]
    ) as patch_get_table_cols, patch.object(
        process_functions, "_create_schema", return_value=new_table_ent
    ) as patch_create_schema, patch.object(
        process_functions, "_update_database_mapping", return_value=update_return
    ) as patch_update, patch.object(
        process_functions, "_move_entity", return_value=move_entity_return
    ) as patch_move, patch.object(
        process_functions.time, "time", return_value=2
    ):
        new_table = process_functions.create_new_fileformat_table(
            syn, fileformat, new_table_name, project_id, archived_project_id
        )
        patch_getdb.assert_called_once_with(syn, project_id)
        patch_syn_get.assert_called_once_with(db_synid)
        patch_get_table_cols.assert_called_once_with(db_synid)
        patch_create_schema.assert_called_once_with(
            syn,
            table_name=new_table_name,
            columns=["foo", "ddooo"],
            parentid=project_id,
            annotations=table_ent.annotations,
        )
        patch_update.assert_called_once_with(
            syn, database_mappingdf, "syn666", fileformat, new_table_ent.id
        )
        patch_move.assert_called_once_with(
            syn, table_ent, archived_project_id, name="ARCHIVED 2-foo"
        )
        assert new_table == {
            "newdb_ent": new_table_ent,
            "newdb_mappingdf": update_return,
            "moved_ent": move_entity_return,
        }


class TestCheckColAndValues:
    @pytest.mark.parametrize(
        "test_input",
        [
            pd.DataFrame({"some_col": ["Val1", "Val2", "val1"]}),
            pd.DataFrame({"some_col": ["Val1", "Val2", "Val3"]}),
            pd.DataFrame({"some_col": [None, "Val1", "Val2"]}),
            pd.DataFrame({"some_col": [float("nan"), "Val1", "Val2"]}),
            pd.DataFrame({"some_col": ["VAL1", "Val1", "Val2"]}),
        ],
        ids=[
            "lowercase_invalid_val",
            "extra_invalid_val",
            "none_val",
            "na_val",
            "uppercase_invalid_val",
        ],
    )
    def test_that_func_returns_correct_error_warning_for_str_cols_if_input_has_invalid_vals(
        self,
        test_input,
    ):
        warning, error = process_functions.check_col_and_values(
            df=test_input,
            col="some_col",
            possible_values=["Val1", "Val2"],
            filename="some_file",
            required=False,
        )
        assert error == (
            "some_file: Please double check your some_col column.  This column must only be these values: Val1, Val2\n"
        )
        assert warning == ""

    def test_that_func_returns_correct_error_warning_if_input_col_is_missing_and_required_is_true(
        self,
    ):
        test_input = pd.DataFrame({"some_col2": ["Val1", "Val2"]})
        warning, error = process_functions.check_col_and_values(
            df=test_input,
            col="some_col",
            possible_values=["Val1", "Val2"],
            filename="some_file",
            required=True,
        )
        assert error == "some_file: Must have some_col column.\n"
        assert warning == ""

    def test_that_func_returns_correct_error_warning_if_input_col_is_missing_and_required_is_false(
        self,
    ):
        test_input = pd.DataFrame({"some_col2": ["Val1", "Val2"]})
        warning, error = process_functions.check_col_and_values(
            df=test_input,
            col="some_col",
            possible_values=["Val1", "Val2"],
            filename="some_file",
            required=False,
        )
        assert error == ""
        assert (
            warning
            == "some_file: Doesn't have some_col column. This column will be added\n"
        )

    def test_that_func_returns_correct_error_warning_if_input_col_has_na_and_nas_is_allowed(
        self,
    ):
        test_input = pd.DataFrame({"some_col": ["Val1", "Val2", float("nan"), None]})
        warning, error = process_functions.check_col_and_values(
            df=test_input,
            col="some_col",
            possible_values=["Val1", "Val2"],
            filename="some_file",
            required=False,
            na_allowed=True,
        )
        assert error == ""
        assert warning == ""
