# Test names of data-docs that stay there

From `tests/test_roastery_dataset.py` and `tests/test_roastery_tier3.py` (pinned `d23336d`).

| names | why |
|---|---|
| the 123 twin tests (`test_the_polars_twin_*`, `test_the_spark_twin_*`, `test_the_tab_and_the_no_break_space_are_in_both_twins`) | they hold the Polars and Spark frames to the SQL; the frames live in data-docs |
| `test_the_file_is_plain_utf8_with_unix_line_ends` | about the bytes of `dataset.sql` |
| `test_the_runner_reads_every_table_header_of_the_file` | about the header regex of data-docs' runner |
| `test_the_dataset_holds_the_30_tables_in_their_order`, `test_tier_1_is_the_first_five_tables_of_the_file` | file order; replaced by `test_a_manifest_lists_the_contract_tables_of_its_extract` and `test_contract.py` |
| `test_no_table_has_more_than_six_columns` | replaced by the contract's well-formed test and exact columns in `test_baseline.py` |
| `test_the_builder_writes_one_file_per_table_with_the_counted_rows` | build mechanics; its counts are `COUNTS` in `test_structure.py` |
| `test_a_build_removes_a_parquet_file_no_table_makes`, `test_a_second_build_gives_the_same_bytes` | build mechanics; `test_baseline.py` has its own |
