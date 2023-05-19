import arcpy
import utils.functions
from arcpy import management, analysis
import os
import sys


class Projector(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Projector"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""
        param0 = arcpy.Parameter(
            displayName="Point Feature Class with points to be projected:",
            name="project_points",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Point", "Multipoint"]

        param1 = arcpy.Parameter(
            displayName="Point Feature Class with river distance:",
            name="distance_points",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param1.filter.list = ["Point", "Multipoint"]

        param2 = arcpy.Parameter(
            displayName="River Distance Field:",
            name="distance_field",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param2.filter.list = ["Short", "Long", "Float", "Single", "Double"]
        param2.parameterDependencies = [param1.name]

        param3 = arcpy.Parameter(
            displayName="Polygon Feature Class with zones:",
            name="zone_polygons",
            datatype="GPFeatureLayer",
            parameterType="Optional",
            direction="Input")
        param3.filter.list = ['Polygon']

        param4 = arcpy.Parameter(
            displayName="Zone Name Field:",
            name="zone_field",
            datatype="Field",
            parameterType="Optional",
            direction="Input",
            enabled=False)
        param4.filter.list = ["Text"]
        param4.parameterDependencies = [param3.name]

        param5 = arcpy.Parameter(
            displayName="Output feature class:",
            name="output_projected_points",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        param6 = arcpy.Parameter(
            displayName="Raster or mosaic with elevation values (DEM):",
            name="DEM",
            datatype=["GPMosaicLayer", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param7 = arcpy.Parameter(
            displayName="Remove projected points with no river distance value",
            name="remove_nulls",
            datatype="Boolean",
            parameterType="Optional",
            direction="Input")

        param8 = arcpy.Parameter(
            displayName="Include Projection Lines",
            name="include_projection_lines",
            datatype="Boolean",
            parameterType="Optional",
            direction="Input")

        param9 = arcpy.Parameter(
            displayName="Output Projection Line Feature Class:",
            name="output_projection_lines_fc",
            datatype="DEFeatureClass",
            parameterType="Optional",
            direction="Output",
            enabled=False)

        params = [param0, param1, param2, param3, param4, param5, param6, param7, param8, param9]

        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        zones_file = parameters[3].value
        zone_name = parameters[4]
        include_projection = parameters[8].value
        projection_lines = parameters[9]

        if zones_file is None:
            utils.functions.deactivate(zone_name)
        else:
            zone_name.enabled = True

        if not include_projection:
            utils.functions.deactivate(projection_lines)
        else:
            projection_lines.enabled = True

        arcpy.env.overwriteOutput = True
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
            parameter.  This method is called after internal validation."""
        zones_file = parameters[3].value
        zone_name = parameters[4]
        include_projection = parameters[8].value
        projection_lines = parameters[9]

        if zones_file is not None and zone_name.value is None:
            zone_name.setIDMessage("Error", "530")

        if zones_file is None or zone_name.value is not None:
            zone_name.clearMessage()

        if include_projection and projection_lines.value is None:
            projection_lines.setIDMessage("Error", "530")

        if not include_projection or projection_lines.value is not None:
            projection_lines.clearMessage()

        return

    def execute(self, parameters, messages):
        arcpy.env.overwriteOutput = True
        messages.addMessage("getting things started ...")

        # Assign tool parameters
        to_project_fc = parameters[0].valueAsText
        distance_fc = parameters[1].valueAsText
        distance_field = parameters[2].valueAsText
        zone_fc = parameters[3].valueAsText
        zone_field = parameters[4].valueAsText
        output_fc = parameters[5].valueAsText
        dem = parameters[6].valueAsText
        remove_nulls = parameters[7].value
        include_projection = parameters[8].value
        projection_lines_fc = parameters[9].valueAsText

        # Runs the Near, Join, and Extract tools on points to be projected.
        # All of these tools modify the input, and so can all be run on the same input feature class
        def near_join_extract(projected, river, distance, elevation):
            messages.addMessage("Finding closest points ...")
            arcpy.analysis.Near(in_features=projected,
                                near_features=river,
                                search_radius="#",
                                location="LOCATION",
                                angle="ANGLE",
                                method="PLANAR")
            messages.addMessage("Joining ...")
            arcpy.management.JoinField(in_data=projected,
                                       in_field="NEAR_FID",
                                       join_table=river,
                                       join_field="OBJECTID",
                                       fields=distance)
            messages.addMessage("Extracting elevation...")
            arcpy.sa.ExtractMultiValuesToPoints(projected, elevation, "NONE")

        # Retrieves script errors, used for except statements
        def gp_error():
            e = sys.exc_info()[1]
            messages.addErrorMessage(e.args[0])

        # When a user does not specify zones. Split is not performed
        # Intermediates are written to memory, and deleted if there is an error, or when processing finishes
        # The final output is saved to disk
        if zone_fc is None:
            try:
                output = arcpy.management.CopyFeatures(to_project_fc, r'memory\to_project_fc')
                near_join_extract(output, distance_fc, distance_field, dem)
            except arcpy.ExecuteError:
                arcpy.management.Delete('memory/')
                gp_error()
                return
            arcpy.management.CopyFeatures(output, output_fc)
            arcpy.management.Delete('memory/')

        # When a user does specify zones, split the input point features before performing near_join_extract
        # Intermediates are written to memory, and deleted if there is an error, or when processing finishes
        # The final output is saved to disk
        if zone_fc is not None:
            try:
                # Copy zones to memory and rename the zone name fields.
                # The split tool will use the zone names as the output feature class names.
                zone_mem = arcpy.management.CopyFeatures(zone_fc, r'memory\zone_mem')
                with arcpy.da.UpdateCursor(zone_mem, [zone_field]) as cursor:
                    for row in cursor:
                        row[0] = f'{row[0]}_pt'
                        cursor.updateRow(row)

                # Split Points to be projected based on zones. Each will be named as zoneName_pt
                messages.addMessage("Splitting points based on zones ...")
                arcpy.analysis.Split(in_features=to_project_fc,
                                     split_features=zone_mem,
                                     split_field=zone_field,
                                     out_workspace=r'memory/',
                                     cluster_tolerance="#")

                # Rename the zones again, this time for splitting river distance.
                with arcpy.da.UpdateCursor(zone_mem, [zone_field]) as cursor:
                    for row in cursor:
                        row[0] = f'{row[0][0:-3]}_mi'
                        cursor.updateRow(row)

                # Split river distances into zones. Each will be named as zoneName_mi
                messages.addMessage("Splitting miles based on zones ...")
                arcpy.analysis.Split(in_features=distance_fc,
                                     split_features=zone_mem,
                                     split_field=zone_field,
                                     out_workspace=r'memory/',
                                     cluster_tolerance="#")

                # Get a list of feature classes corresponding to the split points to be projected
                # This gets us a zones list
                arcpy.env.workspace = r'memory/'
                zones_list = [fc for fc in arcpy.ListFeatureClasses() if fc.endswith('_pt')]
                zones = [zone[0:-3] for zone in zones_list]
                messages.addMessage(f'Zones: {zones}')
            except arcpy.ExecuteError:
                gp_error()
                arcpy.management.Delete(r'memory/')
                return

            # For each projected point feature class in each zone, get the corresponding river distance feature class
            # Then run through the near_join_extract function
            for item in zones_list:
                base_item = item[0:-3]
                split_point = os.path.join(r'memory/', item)
                split_distance = os.path.join(r'memory/', f'{base_item}_mi')
                if arcpy.Exists(split_point) and arcpy.Exists(split_distance):
                    try:
                        messages.addMessage("Working on zone: " + str(base_item))
                        near_join_extract(split_point, split_distance, distance_field, dem)

                        # Combine the results. Use merge when the first near_join_extract is done to create the output
                        # After the output is already created, use append to add new results
                        # This is all written to disk
                        if arcpy.Exists(output_fc):
                            arcpy.management.Append(inputs=split_point, target=output_fc)
                        else:
                            arcpy.management.Merge(inputs=split_point, output=output_fc)
                    except arcpy.ExecuteError:
                        gp_error()
                        arcpy.management.Delete(r'memory/')
                        if arcpy.Exists(output_fc):
                            arcpy.management.Delete(output_fc)
                        return
                else:
                    if not arcpy.Exists(split_point):
                        messages.addErrorMessage(f'For zone {base_item}, the points to project feature class '
                                                 f'is missing.')
                    if not arcpy.Exists(split_distance):
                        messages.addErrorMessage(f'For zone {base_item}, the river distance feature class '
                                                 f'is missing.')
                    arcpy.management.Delete(r'memory/')
                    return
            arcpy.management.Delete(r'memory/')

        # If the user wants to remove projected points with no river values.
        # Add a message corresponding to the number of points removed.
        if remove_nulls:
            count = 0
            with arcpy.da.UpdateCursor(output_fc, [distance_field]) as cursor:
                for row in cursor:
                    if row[0] is None:
                        count += 1
                        cursor.deleteRow()
            if count == 1:
                messages.addMessage(f'{count} projected point with no distance value was deleted.')
            elif count > 1:
                messages.addMessage(f'{count} projected points with no distance values were deleted.')
            else:
                messages.addMessage('All projected points have a distance value, none were deleted.')

        # If the user wants to include projection lines, run through the steps
        # The projected points output is copied to memory, only the final output is saved back to the disk.
        if include_projection:
            messages.addMessage('Creating projection lines feature class...')
            try:
                projector_output_mem = arcpy.management.CopyFeatures(output_fc, r'memory\output_fc')
                arcpy.management.CalculateGeometryAttributes(
                    in_features=projector_output_mem,
                    geometry_property=[["POINT_X", "POINT_X"], ["POINT_Y", "POINT_Y"]])
                arcpy.management.XYToLine(
                    in_table=projector_output_mem,
                    out_featureclass=projection_lines_fc,
                    startx_field="POINT_X",
                    starty_field="POINT_Y",
                    endx_field="NEAR_X",
                    endy_field="NEAR_Y")
            except arcpy.ExecuteError:
                gp_error()
                arcpy.management.Delete(r'memory/')
                return

            arcpy.management.Delete(r'memory/')

        arcpy.env.overwriteOutput = False
        messages.addMessage("All Done!")
        return


class MapUnitZonalStats(object):
    def __init__(self):
        """Define the tool (tool name is the name of the class)."""
        self.label = "Map Unit Zonal Stats"
        self.description = ""
        self.canRunInBackground = False

    def getParameterInfo(self):
        """Define parameter definitions"""

        param0 = arcpy.Parameter(
            displayName="Map Unit Polygons:",
            name="map_units",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Polygon"]

        param1 = arcpy.Parameter(
            displayName="Zone Name Field:",
            name="zone_field",
            datatype="Field",
            parameterType="Required",
            direction="Input",
            enabled=False)

        param1.parameterDependencies = [param0.name]
        param1.filter.list = ["Text", "Short", "Long"]

        param2 = arcpy.Parameter(
            displayName="Raster or mosaic with elevation values (DEM):",
            name="DEM",
            datatype=["GPMosaicLayer", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param3 = arcpy.Parameter(
            displayName="Output Feature Class:",
            name="output_fc",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        params = [param0, param1, param2, param3]
        return params

    def isLicensed(self):
        """Set whether tool is licensed to execute."""
        return True

    def updateParameters(self, parameters):
        """Modify the values and properties of parameters before internal
        validation is performed.  This method is called whenever a parameter
        has been changed."""
        map_units = parameters[0].value
        zone_field = parameters[1]

        if map_units is None:
            utils.functions.deactivate(zone_field)
        else:
            zone_field.enabled = True

        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        map_units = parameters[0].valueAsText
        zone_field = parameters[1].valueAsText
        dem = parameters[2].valueAsText
        output_fc = parameters[3].valueAsText

        # Retrieves script errors, used for exceptions
        def gp_error():
            e = sys.exc_info()[1]
            messages.addErrorMessage(e.args[0])

        # Calculate min, max, and mean zonal stats for an input polygon layer with an identifying zone field.
        # Convert the polygon to points, then add the zonal stats with join field to those points
        # Save intermediates to memory, copy the final output to disk
        # Clear memory at the end of the script, or if an error is encountered
        arcpy.management.Delete(r'memory/')
        try:
            messages.addMessage("Calculating zonal statistics...")
            map_unit_stats = arcpy.sa.ZonalStatisticsAsTable(in_zone_data=map_units,
                                                             zone_field=zone_field,
                                                             in_value_raster=dem,
                                                             out_table=r'memory\map_unit_stats',
                                                             statistics_type="MIN_MAX_MEAN",
                                                             percentile_interpolation_type="AUTO_DETECT"
                                                             )

            messages.addMessage("Converting polygons to points...")
            statistics_points = arcpy.management.FeatureToPoint(map_units, r'memory\statistics_point')

            messages.addMessage("Adding zonal statistics to points...")
            arcpy.management.JoinField(in_data=statistics_points,
                                       in_field=zone_field,
                                       join_table=map_unit_stats,
                                       join_field=zone_field,
                                       fields=["MIN", "MAX", "MEAN"]
                                       )

            messages.addMessage("Saving output...")
            arcpy.management.CopyFeatures(statistics_points, output_fc)
        except arcpy.ExecuteError:
            gp_error()
            arcpy.management.Delete(r'memory/')
            return

        arcpy.management.Delete(r'memory/')
        return
