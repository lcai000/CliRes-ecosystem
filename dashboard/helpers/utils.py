def get_base_col_name(column_name):
    if isinstance(column_name, str):
        return column_name.rsplit('_', 1)[0] if '_' in column_name else column_name
    return column_name
