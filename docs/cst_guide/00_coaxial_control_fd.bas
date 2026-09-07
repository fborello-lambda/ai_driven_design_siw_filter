' Standalone coax control, 12 mm, nominal 50 ohm.
' FDSolver block below is UNVERIFIED -- report exact error line if CST rejects it.
Option Explicit
Sub Main
ResetAll
AddToHistory "units", "With Units" & vbLf & _
  ".Geometry ""mm""" & vbLf & _
  ".Frequency ""GHz""" & vbLf & _
  ".Time ""ns""" & vbLf & _
  "End With"
AddToHistory "frequency", "Solver.FrequencyRange ""2.0"", ""3.6"""
AddToHistory "PTFE", "With Material" & vbLf & _
  ".Reset" & vbLf & _
  ".Name ""PTFE_sma""" & vbLf & _
  ".Folder """"" & vbLf & _
  ".Type ""Normal""" & vbLf & _
  ".Epsilon ""2.08""" & vbLf & _
  ".Mu ""1""" & vbLf & _
  ".TanD ""0.0004""" & vbLf & _
  ".TanDFreq ""2.87""" & vbLf & _
  ".TanDGiven ""True""" & vbLf & _
  ".TanDModel ""ConstTanD""" & vbLf & _
  ".Create" & vbLf & _
  "End With"
AddToHistory "pin", "With Cylinder" & vbLf & _
  ".Reset" & vbLf & _
  ".Name ""pin""" & vbLf & _
  ".Component ""component1""" & vbLf & _
  ".Material ""PEC""" & vbLf & _
  ".Axis ""x""" & vbLf & _
  ".Outerradius ""0.3800""" & vbLf & _
  ".Innerradius ""0.0000""" & vbLf & _
  ".Xrange ""0"", ""12""" & vbLf & _
  ".Ycenter ""0""" & vbLf & _
  ".Zcenter ""0""" & vbLf & _
  ".Segments ""0""" & vbLf & _
  ".Create" & vbLf & _
  "End With"
AddToHistory "ptfe", "With Cylinder" & vbLf & _
  ".Reset" & vbLf & _
  ".Name ""ptfe""" & vbLf & _
  ".Component ""component1""" & vbLf & _
  ".Material ""PTFE_sma""" & vbLf & _
  ".Axis ""x""" & vbLf & _
  ".Outerradius ""1.2639""" & vbLf & _
  ".Innerradius ""0.3800""" & vbLf & _
  ".Xrange ""0"", ""12""" & vbLf & _
  ".Ycenter ""0""" & vbLf & _
  ".Zcenter ""0""" & vbLf & _
  ".Segments ""0""" & vbLf & _
  ".Create" & vbLf & _
  "End With"
AddToHistory "shield", "With Cylinder" & vbLf & _
  ".Reset" & vbLf & _
  ".Name ""shield""" & vbLf & _
  ".Component ""component1""" & vbLf & _
  ".Material ""PEC""" & vbLf & _
  ".Axis ""x""" & vbLf & _
  ".Outerradius ""1.5639""" & vbLf & _
  ".Innerradius ""1.2639""" & vbLf & _
  ".Xrange ""0"", ""12""" & vbLf & _
  ".Ycenter ""0""" & vbLf & _
  ".Zcenter ""0""" & vbLf & _
  ".Segments ""0""" & vbLf & _
  ".Create" & vbLf & _
  "End With"
AddToHistory "background", "With Background" & vbLf & _
  ".ResetBackground" & vbLf & _
  ".Type ""Normal""" & vbLf & _
  ".XminSpace ""0""" & vbLf & _
  ".XmaxSpace ""0""" & vbLf & _
  ".YminSpace ""2""" & vbLf & _
  ".YmaxSpace ""2""" & vbLf & _
  ".ZminSpace ""2""" & vbLf & _
  ".ZmaxSpace ""2""" & vbLf & _
  "End With"
AddToHistory "boundaries", "With Boundary" & vbLf & _
  ".Xmin ""open""" & vbLf & _
  ".Xmax ""open""" & vbLf & _
  ".Ymin ""open""" & vbLf & _
  ".Ymax ""open""" & vbLf & _
  ".Zmin ""open""" & vbLf & _
  ".Zmax ""open""" & vbLf & _
  ".ApplyInAllDirections ""False""" & vbLf & _
  "End With"
AddToHistory "coax port 1", "With Port" & vbLf & _
  ".Reset" & vbLf & _
  ".PortNumber ""1""" & vbLf & _
  ".NumberOfModes ""1""" & vbLf & _
  ".Coordinates ""Free""" & vbLf & _
  ".Orientation ""xmin""" & vbLf & _
  ".PortOnBound ""True""" & vbLf & _
  ".Xrange ""0"", ""0""" & vbLf & _
  ".Yrange ""-1.5639"", ""1.5639""" & vbLf & _
  ".Zrange ""-1.5639"", ""1.5639""" & vbLf & _
  ".Create" & vbLf & _
  "End With"
AddToHistory "coax port 2", "With Port" & vbLf & _
  ".Reset" & vbLf & _
  ".PortNumber ""2""" & vbLf & _
  ".NumberOfModes ""1""" & vbLf & _
  ".Coordinates ""Free""" & vbLf & _
  ".Orientation ""xmax""" & vbLf & _
  ".PortOnBound ""True""" & vbLf & _
  ".Xrange ""12"", ""12""" & vbLf & _
  ".Yrange ""-1.5639"", ""1.5639""" & vbLf & _
  ".Zrange ""-1.5639"", ""1.5639""" & vbLf & _
  ".Create" & vbLf & _
  "End With"
AddToHistory "define mesh settings", "With Mesh" & vbLf & _
  ".MeshType ""Tetrahedral""" & vbLf & _
  ".SetCreator ""High Frequency""" & vbLf & _
  "End With"
AddToHistory "define frequency domain solver parameters", "With FDSolver" & vbLf & _
  ".Reset" & vbLf & _
  ".SetMethod ""Tetrahedral"", ""General purpose""" & vbLf & _
  ".MeshAdaptionTet ""True""" & vbLf & _
  ".MeshAdaptionHex ""False""" & vbLf & _
  ".Stimulation ""All"", ""All""" & vbLf & _
  "End With"
MsgBox "Coax control built. Select Frequency Domain Solver and inspect both TEM port modes, then Start."
End Sub
