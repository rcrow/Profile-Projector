import arcpy
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
            parameterType="Optional",
            direction="Input")
        param2.filter.list = ["Short", "Long", "Float", "Single", "Double"]
        param2.parameterDependencies = [param1.name]

        param3 = arcpy.Parameter(
            displayName="Polygon Feature Class with zones:",
            name="zonesFile",
            datatype="GPFeatureLayer",
            parameterType="Required",
            direction="Input")
        param3.filter.list = ['Polygon']

        param4 = arcpy.Parameter(
            displayName="Zone Name Field:",
            name="zone",
            datatype="Field",
            parameterType="Optional",
            direction="Input")
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
        arcpy.env.overwriteOutput = True
        return

    def updateMessages(self, parameters):
        """Modify the messages created by internal validation for each tool
        parameter.  This method is called after internal validation."""
        return

    def execute(self, parameters, messages):
        arcpy.env.overwriteOutput = True
        messages.addMessage("getting things started ...")
        # Assign variables
        zonesList = None
        zonesFile = parameters[2].valueAsText
        milesFile = parameters[1].valueAsText
        toProjectFile = parameters[0].valueAsText
        OutputFeatureClass = parameters[3].valueAsText
        dem = parameters[4].valueAsText

        miles_spatial = arcpy.Describe(parameters[1].value).spatialReference
        to_project_spatial = arcpy.Describe(parameters[0].value).spatialReference

        arcpy.management.CreateFeatureDataset(arcpy.env.scratchWorkspace, "MilesSplit",
                                              miles_spatial)
        arcpy.management.CreateFeatureDataset(arcpy.env.scratchWorkspace, "PointsSplit",
                                              to_project_spatial)

        scratch = arcpy.env.scratchWorkspace

        # Split Points of Interest into zones
        messages.addMessage("Splitting points based on zones ...")
        arcpy.analysis.Split(in_features=toProjectFile, split_features=zonesFile, split_field="Name",
                             out_workspace=scratch + "/PointsSplit", cluster_tolerance="#")

        # Rename feature classes
        arcpy.env.workspace = scratch
        pointsList = arcpy.ListFeatureClasses('', '', "PointsSplit")
        # messages.addMessage(pointsList)
        for stuff in pointsList:
            arcpy.management.Rename(str(stuff), str(stuff) + "_pt")

        # Split Miles into zones
        messages.addMessage("Splitting miles based on zones ...")
        arcpy.analysis.Split(in_features=milesFile, split_features=zonesFile, split_field="Name",
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
                                           join_field="OBJECTID", fields="RM_final")
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

        # arcpy.management.Merge(inputs="E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt;E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt",output="E:/users/rcrow/Documents/ArcGIS/Default.gdb/Blythe_pt_Merge",field_mappings="""SampNum "SampNum" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,SampNum,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,SampNum,-1,-1;Area "Area" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,Area,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,Area,-1,-1;Person "Person" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,Person,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,Person,-1,-1;Material "Material" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,Material,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,Material,-1,-1;StatUnit "StatUnit" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,StatUnit,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,StatUnit,-1,-1;Notes "Notes" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,Notes,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,Notes,-1,-1;Date "Date" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,Date,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,Date,-1,-1;OrigX "OrigX" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,OrigX,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,OrigX,-1,-1;OrigY "OrigY" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,OrigY,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,OrigY,-1,-1;XYerror "XYerror" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,XYerror,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,XYerror,-1,-1;ErrorUnit "ErrorUnit" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,ErrorUnit,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,ErrorUnit,-1,-1;OrigDat "OrigDat" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,OrigDat,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,OrigDat,-1,-1;OrigCS "OrigCS" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,OrigCS,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,OrigCS,-1,-1;XYmeth "XYmeth" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,XYmeth,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,XYmeth,-1,-1;Long "Long" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,Long,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,Long,-1,-1;Lat "Lat" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,Lat,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,Lat,-1,-1;LocConv "LocConv" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,LocConv,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,LocConv,-1,-1;OrigElev "OrigElev" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,OrigElev,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,OrigElev,-1,-1;ElevMeth "ElevMeth" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,ElevMeth,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,ElevMeth,-1,-1;Elev "Elev" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,Elev,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,Elev,-1,-1;ElevSource "ElevSource" true true false 255 Text 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,ElevSource,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,ElevSource,-1,-1;NEAR_FID "NEAR_FID" true true false 4 Long 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,NEAR_FID,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,NEAR_FID,-1,-1;NEAR_DIST "NEAR_DIST" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,NEAR_DIST,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,NEAR_DIST,-1,-1;NEAR_X "NEAR_X" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,NEAR_X,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,NEAR_X,-1,-1;NEAR_Y "NEAR_Y" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,NEAR_Y,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,NEAR_Y,-1,-1;NEAR_ANGLE "NEAR_ANGLE" true true false 8 Double 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,NEAR_ANGLE,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,NEAR_ANGLE,-1,-1;RM_final "RM_final" true true false 2 Short 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,RM_final,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,RM_final,-1,-1;TERRAIN_DEM10Meter_LOCO "TERRAIN_DEM10Meter_LOCO" true true false 4 Float 0 0 ,First,#,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Blythe_pt,TERRAIN_DEM10Meter_LOCO,-1,-1,E:/users/rcrow/Documents/ArcGIS/Default.gdb/PointsSplit/Laughlin_pt,TERRAIN_DEM10Meter_LOCO,-1,-1""")

        arcpy.management.Merge(inputs=inputsString, output=OutputFeatureClass)

        arcpy.management.Delete(in_data=scratch + "/MilesSplit", data_type="FeatureDataset")
        arcpy.management.Delete(in_data=scratch + "/PointsSplit", data_type="FeatureDataset")

        removeNulls = parameters[5].valueAsText
        if removeNulls == "true":
            # For testing
            fields = arcpy.ListFields(OutputFeatureClass)
            for field in fields:
                arcpy.AddMessage("{0} is a type of {1} with a length of {2}"
                                 .format(field.name, field.type, field.length))

            with arcpy.da.UpdateCursor(OutputFeatureClass, ['RM_final']) as cursor:

                for row in cursor:
                    arcpy.AddMessage(row)
                    if row[0] == None:
                        # TODO instead of deleting these consider populating MIN, MAX, and MEAN with the value extracted from a DEM at the point
                        cursor.deleteRow()

        arcpy.env.overwriteOutput = False
        messages.addMessage("All Done!")
        return
