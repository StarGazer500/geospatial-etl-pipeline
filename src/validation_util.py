from data_management_util import DataManagement


class Validation:

    layers_val_info = None

    @classmethod
    def load_validation_rules(cls, conn):
        if cls.layers_val_info is None:
            validation = DataManagement.execute_query_non_spatial(
                conn,
                "SELECT * FROM validation.column_type_requirements",
            )
            cls.layers_val_info = validation



    @classmethod
    def check_layer_name(cls, conn, project_schema):

        project_data = DataManagement.execute_query_non_spatial(
            conn,
            f"""
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = '{project_schema}'
            ORDER BY table_name
            """
        )

        expected_layers = set(cls.layers_val_info['table_name'])
        project_layers = list(project_data['table_name'])
        layer_check = {f"{project_schema}_layers": project_layers, "expected_layers": [], "matching_layers": [], "other_required_layers": []}

        if project_schema == "akwaaba_schema":
            akwaaba_expected_layers = expected_layers
            for layer in akwaaba_expected_layers:
                if layer in project_layers:
                    layer_check["matching_layers"].append(layer)
                else:
                    layer_check["other_required_layers"].append(layer)
            layer_check['expected_layers'] = list(expected_layers)

        elif project_schema == "buffalo_schema":
            buffalo_expected_layers = [x for x in expected_layers if x not in ("intercropped_farms", "field_mapped_farms")]
            for layer in buffalo_expected_layers:
                if layer in project_layers:
                    layer_check["matching_layers"].append(layer)
                else:
                    layer_check["other_required_layers"].append(layer)
            layer_check['expected_layers'] = buffalo_expected_layers

        elif project_schema == "colobus_schema":
            colobus_expected_layers = [x for x in expected_layers if x not in ("intercropped_farms",)]
            for layer in colobus_expected_layers:
                if layer in project_layers:
                    layer_check["matching_layers"].append(layer)
                else:
                    layer_check["other_required_layers"].append(layer)
            layer_check['expected_layers'] = colobus_expected_layers

        return layer_check



    @classmethod
    def check_column_name(cls, conn, project_schema, layer_check):
        layers_column_check_info = {}
        for layer in layer_check["matching_layers"]:
            required_layer_info = cls.layers_val_info[cls.layers_val_info['table_name'] == layer]
            expected_layer_columns = required_layer_info.column_name
            project_layer = DataManagement.execute_spatial_query(
                conn,
                f"SELECT * FROM {project_schema}.{layer}",
                geom_col='geom'
            )
            project_layer_columns = project_layer.columns
            column_check = {f"{layer}_columns": list(project_layer_columns), "expected_columns": list(expected_layer_columns), "matching_columns": [], "other_required_columns": []}
            for column in expected_layer_columns:
                if column in project_layer_columns:
                    column_check["matching_columns"].append(column)
                else:
                    column_check["other_required_columns"].append(column)
            layers_column_check_info[layer] = column_check

        return layers_column_check_info



    @classmethod
    def validate_schema(cls, val_conn,project_db_conn, schema):
        cls.load_validation_rules(val_conn)

        # Layer Check
        layer_check_result = cls.check_layer_name(project_db_conn, schema)
        if layer_check_result["other_required_layers"]:
            print('Layer name validation failed')
            print(f"Missing layers: {layer_check_result['other_required_layers']}")
            return False

        # Column check
        column_check_result = cls.check_column_name(project_db_conn, schema, layer_check=layer_check_result)

        # Check if any layers have missing columns
        layers_with_missing_columns = []
        for layer, column_info in column_check_result.items():
            if column_info["other_required_columns"]:
                layers_with_missing_columns.append({
                    "layer": layer,
                    "missing_columns": column_info["other_required_columns"]
                })

        if layers_with_missing_columns:
            print('Column name validation failed')
            for layer_info in layers_with_missing_columns:
                print(f"Layer '{layer_info['layer']}' missing columns: {layer_info['missing_columns']}")
            return False

        # All validations passed
        print('Schema validation passed!')
        return True



    @staticmethod
    def validate_and_fix_geometries(gdf, verbose=True):
        """
        Check if all geometries are valid, if not fix them.

        Parameters:
        -----------
        gdf : GeoDataFrame
        verbose : bool, default True
            Print diagnostic information

        Returns:
        --------
        GeoDataFrame with all valid geometries
        """

        # Remove null and empty geometries
        gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()

        # Check if fixing is needed
        invalid_count = (~gdf.geometry.is_valid).sum()

        if invalid_count > 0:
            if verbose:
                print(f"Fixing {invalid_count} invalid geometries...")

            geom_col = gdf.geometry.name
            gdf[geom_col] = gdf.geometry.make_valid()

            # Remove any that couldn't be fixed
            gdf = gdf[gdf.geometry.is_valid].copy()

        if verbose:
            print(f"All geometries valid: {gdf.geometry.is_valid.all()}")

        return gdf
