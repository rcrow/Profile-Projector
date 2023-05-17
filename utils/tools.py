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

        def near_join(projected, river, distance, elevation):
            messages.addMessage("Finding closest points ...")
            near = arcpy.analysis.Near(in_features=projected, near_features=river,
                                       search_radius="#", location="LOCATION",
                                       angle="ANGLE", method="PLANAR")
            messages.addMessage("Joining ...")
            join = arcpy.management.JoinField(in_data=near, in_field="NEAR_FID",
                                              join_table=river, join_field="OBJECTID",
                                              fields=distance)
            messages.addMessage("Extracting elevation...")
            arcpy.sa.ExtractMultiValuesToPoints(join, elevation, "NONE")

        if zone_fc is None:
            try:
                output = arcpy.management.Copy(to_project_fc, output_fc)
                near_join(output, distance_fc, distance_field, dem)
            except arcpy.ExecuteError:
                if arcpy.Exists(output_fc):
                    arcpy.management.Delete(output_fc)
                e = sys.exc_info()[1]
                messages.addErrorMessage(e.args[0])
                return

        if zone_fc is not None:
            miles_spatial = arcpy.Describe(parameters[1].value).spatialReference
            to_project_spatial = arcpy.Describe(parameters[0].value).spatialReference

            def feature_dataset(workspace, name, projection):
                fd_result = arcpy.management.CreateFeatureDataset(workspace, name, projection)
                return str(fd_result)

            points_fd_name = "PointsSplit"
            points_fd = feature_dataset(arcpy.env.scratchWorkspace, points_fd_name, miles_spatial)
            distance_fd_name = "MilesSplit"
            distance_fd = feature_dataset(arcpy.env.scratchWorkspace, distance_fd_name, to_project_spatial)

            scratch = arcpy.env.scratchWorkspace

            # Split Points of Interest into zones
            messages.addMessage("Splitting points based on zones ...")
            arcpy.analysis.Split(in_features=to_project_fc, split_features=zone_fc, split_field=zone_field,
                                 out_workspace=points_fd, cluster_tolerance="#")

            # Rename feature classes
            arcpy.env.workspace = scratch
            points_list = arcpy.ListFeatureClasses('', '', points_fd_name)
            # messages.addMessage(pointsList)
            for stuff in points_list:
                arcpy.management.Rename(str(stuff), str(stuff) + "_pt")

            # Split Miles into zones
            messages.addMessage("Splitting miles based on zones ...")
            arcpy.analysis.Split(in_features=distance_fc, split_features=zone_fc, split_field=zone_field,
                                 out_workspace=distance_fd, cluster_tolerance="#")

            # Rename feature classes
            arcpy.env.workspace = scratch
            miles_list = arcpy.ListFeatureClasses('', '', distance_fd_name)
            messages.addMessage(miles_list)
            for junk in miles_list:
                arcpy.management.Rename(str(junk), str(junk) + "_mi")

            # Find zones with points for projection
            zones_list = arcpy.ListFeatureClasses('', '', points_fd_name)
            messages.addMessage(zones_list)

            # Find zones with points for projection
            for item in zones_list:
                split_point = os.path.join(points_fd, item)
                split_distance = os.path.join(distance_fd, f'{item[0:-3]}_mi')
                if arcpy.Exists(split_point) and arcpy.Exists(split_distance):
                    messages.addMessage("Working on zone: " + str(item))
                    near_join(split_point, split_distance, distance_field, dem)
                    if arcpy.Exists(output_fc):
                        arcpy.management.Append(inputs=split_point, target=output_fc)
                    else:
                        arcpy.management.Merge(inputs=split_point, output=output_fc)

            arcpy.management.Delete(in_data=distance_fd, data_type="FeatureDataset")
            arcpy.management.Delete(in_data=points_fd, data_type="FeatureDataset")

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
            projector_output = arcpy.management.Copy(output_fc)
            line_start = arcpy.management.CalculateGeometryAttributes(
                in_features=projector_output,
                geometry_property=[["POINT_X", "POINT_X"], ["POINT_Y", "POINT_Y"]]
            )
            arcpy.management.XYToLine(
                in_table=line_start,
                out_featureclass=projection_lines_fc,
                startx_field="POINT_X",
                starty_field="POINT_Y",
                endx_field="NEAR_X",
                endy_field="NEAR_Y"
            )
            arcpy.management.Delete(line_start)

        arcpy.env.overwriteOutput = False
        messages.addMessage("All Done!")
        return
