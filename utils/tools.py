import arcpy
import utils.functions
from arcpy import management, analysis


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
            name="toProjectFile",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param0.filter.list = ["Point", "Multipoint"]

        param1 = arcpy.Parameter(
            displayName="Point Feature Class with river miles:",
            name="milesFile",
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
            name="zonesFile",
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

        params = [param0, param1, param2, param3, param4, param5, param6, param7]

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

        if zones_file is None:
            zone_name.enabled = False
            zone_name.value = None
        else:
            zone_name.enabled = True

        arcpy.env.overwriteOutput = True
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        zones_file = parameters[3].value
        zone_name = parameters[4]

        if zones_file is None or zone_name.value is not None:
            zone_name.clearMessage()

        if zones_file is not None and zone_name.value is None:
            zone_name.setIDMessage("Error", "530")

        return

    def execute(self, parameters, messages):
        arcpy.env.overwriteOutput = True
        messages.addMessage("getting things started ...")
        # Assign variables
        zonesList = None
        zonesFile = parameters[3].valueAsText
        zone_field = parameters[4].valueAsText
        milesFile = parameters[1].valueAsText
        distance_field = parameters[2].valueAsText
        toProjectFile = parameters[0].valueAsText
        OutputFeatureClass = parameters[5].valueAsText
        dem = parameters[6].valueAsText

        def near_join(projected, river, distance_field, dem):
            near = arcpy.analysis.Near(in_features=projected,
                                       near_features=river, search_radius="#",
                                       location="LOCATION", angle="ANGLE", method="PLANAR")

            join = arcpy.management.JoinField(in_data=near, in_field="NEAR_FID",
                                       join_table=river,
                                       join_field="OBJECTID", fields=distance_field)

            arcpy.gp.ExtractMultiValuesToPoints_sa(join, dem, "NONE")

        if zonesFile is None:
            output = arcpy.management.Copy(toProjectFile, OutputFeatureClass)
            near_join(output, milesFile, distance_field, dem)

        if zonesFile is not None:
            miles_spatial = arcpy.Describe(parameters[1].value).spatialReference
            to_project_spatial = arcpy.Describe(parameters[0].value).spatialReference

            arcpy.management.CreateFeatureDataset(arcpy.env.scratchWorkspace, "MilesSplit",
                                                  miles_spatial)
            arcpy.management.CreateFeatureDataset(arcpy.env.scratchWorkspace, "PointsSplit",
                                                  to_project_spatial)

            scratch = arcpy.env.scratchWorkspace

            # Split Points of Interest into zones
            messages.addMessage("Splitting points based on zones ...")
            arcpy.analysis.Split(in_features=toProjectFile, split_features=zonesFile, split_field=zone_field,
                                 out_workspace=scratch + "/PointsSplit", cluster_tolerance="#")

            # Rename feature classes
            arcpy.env.workspace = scratch
            pointsList = arcpy.ListFeatureClasses('', '', "PointsSplit")
            # messages.addMessage(pointsList)
            for stuff in pointsList:
                arcpy.management.Rename(str(stuff), str(stuff) + "_pt")

            # Split Miles into zones
            messages.addMessage("Splitting miles based on zones ...")
            arcpy.analysis.Split(in_features=milesFile, split_features=zonesFile, split_field=zone_field,
                                 out_workspace=scratch + "/MilesSplit", cluster_tolerance="#")

            # Rename feature classes
            arcpy.env.workspace = scratch
            milesList = arcpy.ListFeatureClasses('', '', "MilesSplit")
            messages.addMessage(milesList)
            for junk in milesList:
                arcpy.management.Rename(str(junk), str(junk) + "_mi")

            # Find zones with points for projection
            zonesList = arcpy.ListFeatureClasses('', '', "PointsSplit")
            messages.addMessage(zonesList)

            # Find zones with points for projection
            for item in zonesList:
                if arcpy.Exists(scratch + "/PointsSplit/" + item) and arcpy.Exists(
                        scratch + "/MilesSplit/" + item[0:-3] + "_mi"):
                    messages.addMessage("Working on zone: " + str(item))
                    messages.addMessage("Finding closest points ...")
                    arcpy.analysis.Near(in_features=scratch + "/PointsSplit/" + item,
                                        near_features=scratch + "/MilesSplit/" + item[0:-3] + "_mi", search_radius="#",
                                        location="LOCATION", angle="ANGLE", method="PLANAR")
                    messages.addMessage("Joining ...")
                    arcpy.management.JoinField(in_data=scratch + "/PointsSplit/" + item, in_field="NEAR_FID",
                                               join_table=scratch + "/MilesSplit/" + item[0:-3] + "_mi",
                                               join_field="OBJECTID", fields=distance_field)
                    messages.addMessage("Extracting elevation...")
                    arcpy.gp.ExtractMultiValuesToPoints_sa(scratch + "/PointsSplit/" + item, dem, "NONE")

            # Creat list with full path to output feature classes for merging
            listLength = len(zonesList)
            # messages.addMessage(str(zonesList))
            # messages.addMessage("listLength: "+str(listLength))
            listPaths = [scratch + "\\PointsSplit\\"] * listLength
            # messages.addMessage(str(listPaths))
            mergedList = []

            for x in range(0, listLength):
                # messages.addMessage("x="+str(x))
                mergedList.append(listPaths[x] + zonesList[x])

            inputsString = ';'.join(mergedList)
            messages.addMessage(inputsString)
            messages.addMessage(OutputFeatureClass)

            arcpy.management.Merge(inputs=inputsString, output=OutputFeatureClass)

            arcpy.management.Delete(in_data=scratch + "/MilesSplit", data_type="FeatureDataset")
            arcpy.management.Delete(in_data=scratch + "/PointsSplit", data_type="FeatureDataset")

        removeNulls = parameters[7].valueAsText
        if removeNulls == "true":
            # For testing
            fields = arcpy.ListFields(OutputFeatureClass)
            for field in fields:
                arcpy.AddMessage("{0} is a type of {1} with a length of {2}"
                                 .format(field.name, field.type, field.length))

            with arcpy.da.UpdateCursor(OutputFeatureClass, [distance_field]) as cursor:

                for row in cursor:
                    arcpy.AddMessage(row)
                    if row[0] == None:
                        # TODO instead of deleting these consider populating MIN, MAX, and MEAN with the value extracted from a DEM at the point
                        cursor.deleteRow()

        arcpy.env.overwriteOutput = False
        messages.addMessage("All Done!")
        return
