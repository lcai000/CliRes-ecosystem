def get_base_col_name(column_name):
    """
    Extracts the base name from a potentially aggregated column name.
    Example: 'Girth_cm_mean' -> 'Girth_cm'
    """
    if isinstance(column_name, str):
        return column_name.rsplit('_', 1)[0] if '_' in column_name else column_name
    return column_name