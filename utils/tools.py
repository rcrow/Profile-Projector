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
            name="Points to Project",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Point", "Multipoint"]

        param1 = arcpy.Parameter(
            displayName="Point Feature Class with river miles:",
            name="Points with River Distance",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param1.filter.list = ["Point", "Multipoint"]

        param2 = arcpy.Parameter(
            displayName="River Distance Field:",
            name="distance",
            datatype="Field",
            parameterType="Required",
            direction="Input")
        param2.filter.list = ["Short", "Long", "Float", "Single", "Double"]
        param2.parameterDependencies = [param1.name]

        param3 = arcpy.Parameter(
            displayName="Polygon Feature Class with zones:",
            name="Polygons Denoting Zones",
            datatype="GPFeatureLayer",
            parameterType="Optional",
            direction="Input")
        param3.filter.list = ['Polygon']

        param4 = arcpy.Parameter(
            displayName="Zone Name Field:",
            name="zone",
            datatype="Field",
            parameterType="Optional",
            direction="Input",
            enabled=False)
        param4.filter.list = ["Text"]
        param4.parameterDependencies = [param3.name]

        param5 = arcpy.Parameter(
            displayName="Output feature class:",
            name="OutputFeatureClass",
            datatype="DEFeatureClass",
            parameterType="Required",
            direction="Output")

        param6 = arcpy.Parameter(
            displayName="Individual or raster mosaic with the elevation values (DEM):",
            name="DEM",
            datatype=["GPMosaicLayer", "GPRasterLayer"],
            parameterType="Required",
            direction="Input")

        param7 = arcpy.Parameter(
            displayName="Remove points with associated profile point?",
            name="removeNulls",
            datatype="Boolean",
            parameterType="Optional",
            direction="Input")

        param8 = arcpy.Parameter(
            displayName="Include Projection Lines",
            name="Projection Lines",
            datatype="Boolean",
            parameterType="Optional",
            direction="Input")

        param9 = arcpy.Parameter(
            displayName="Output Projection Line Feature Class",
            name="Projection Lines Feature",
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

        def near_join_extract(projected, river, distance, elevation):
            messages.addMessage("Finding closest points ...")
            near = arcpy.analysis.Near(in_features=projected,
                                       near_features=river,
                                       search_radius="#",
                                       location="LOCATION",
                                       angle="ANGLE",
                                       method="PLANAR")
            messages.addMessage("Joining ...")
            join = arcpy.management.JoinField(in_data=near,
                                              in_field="NEAR_FID",
                                              join_table=river,
                                              join_field="OBJECTID",
                                              fields=distance)
            messages.addMessage("Extracting elevation...")
            arcpy.sa.ExtractMultiValuesToPoints(join, elevation, "NONE")

        def gp_error():
            e = sys.exc_info()[1]
            messages.addErrorMessage(e.args[0])

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

        if zone_fc is not None:
            try:
                zone_mem = arcpy.management.CopyFeatures(zone_fc, r'memory\zone_mem')
                with arcpy.da.UpdateCursor(zone_mem, [zone_field]) as cursor:
                    for row in cursor:
                        row[0] = f'{row[0]}_pt'
                        cursor.updateRow(row)

                # Split Points of Interest into zones
                messages.addMessage("Splitting points based on zones ...")
                arcpy.analysis.Split(in_features=to_project_fc,
                                     split_features=zone_mem,
                                     split_field=zone_field,
                                     out_workspace=r'memory/',
                                     cluster_tolerance="#")

                with arcpy.da.UpdateCursor(zone_mem, [zone_field]) as cursor:
                    for row in cursor:
                        row[0] = f'{row[0][0:-3]}_mi'
                        cursor.updateRow(row)

                # Split Miles into zones
                messages.addMessage("Splitting miles based on zones ...")
                arcpy.analysis.Split(in_features=distance_fc,
                                     split_features=zone_mem,
                                     split_field=zone_field,
                                     out_workspace=r'memory/',
                                     cluster_tolerance="#")

                # Find zones with points for projection
                arcpy.env.workspace = r'memory/'
                zones_list = [fc for fc in arcpy.ListFeatureClasses() if fc.endswith('_pt')]
                zones = [zone[0:-3] for zone in zones_list]
                messages.addMessage(f'Zones: {zones}')
            except arcpy.ExecuteError:
                gp_error()
                arcpy.management.Delete(r'memory/')
                return

            # Find zones with points for projection
            for item in zones_list:
                base_item = item[0:-3]
                split_point = os.path.join(r'memory/', item)
                split_distance = os.path.join(r'memory/', f'{base_item}_mi')
                if arcpy.Exists(split_point) and arcpy.Exists(split_distance):
                    try:
                        messages.addMessage("Working on zone: " + str(base_item))
                        near_join_extract(split_point, split_distance, distance_field, dem)
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

        if include_projection:
            messages.addMessage('Creating projection lines feature class...')
            try:
                projector_output_mem = arcpy.management.CopyFeatures(output_fc, r'memory\output_fc')
                arcpy.management.CalculateGeometryAttributes(
                    in_features=projector_output_mem,
                    geometry_property=[["POINT_X", "POINT_X"],["POINT_Y", "POINT_Y"]])
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
