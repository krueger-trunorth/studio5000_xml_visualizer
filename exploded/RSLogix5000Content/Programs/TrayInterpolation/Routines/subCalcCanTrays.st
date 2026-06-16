SBR(tempStartLoc,tempAngle,tempOrigin_LL,tempOrigin_SL);
	// check battery type, setup temp variables as LL
	If Machine_Run_Recipe.Battery_type.Value = 0 Then;
		COP(tempOrigin_LL,tempOrigin,1);
		tempXSpacing := rCanTrayXSpacing_LL;
		tempYSpacing := rCanTrayYSpacing_LL;
	End_If;
	// check battery type, setup temp variables as SL
	If Machine_Run_Recipe.Battery_type.Value = 1 Then;
		COP(tempOrigin_SL,tempOrigin,1);
		tempXSpacing := rCanTrayXSpacing_SL;
		tempYSpacing := rCanTrayYSpacing_SL;
	End_If;
	// run nested FOR loop to iterate through trays
	// the order of the for loop matters..
	// iterating thru Y within X sets up the tray
	// (X1,Y1) -> (X1,Y2) -> (X1,Y3) -> (X2,Y1) -> (X2,Y2) etc etc
	For tempXIndex := 1 To 5 By 1 Do;
		For tempYIndex := 1 To 3 By 1 Do;
			// use for loop variables to count along robot indexes, starting at startloc passed into the sub
			// calculated separately to make later code more readable
			// tempXIndex is multiplied by 3 because there are 3 Y indexes!
			tempLocIndex := tempStartLoc + (3*(tempXIndex-1)) + (tempYIndex-1);
			// the main calc's are these
			// the equation is basically
			// X0 = X1*COS(angle)+Y1*-SIN(angle)
			// Y0 = X1*SIN(angle)+Y1*COS(angle)
			// then add back in the origin X&Y
			// angle is inverted so + setting results in CW rotation
			// multiplying by 1000 and placing in integer to try and reduce PLC decimel issues
			tempX := 1000*(tempOrigin.X+((tempXIndex-1)*tempXSpacing*COS(RAD(-tempAngle)))+((tempYIndex-1)*tempYSpacing*-SIN(RAD(-tempAngle))));
			tempY := 1000*(tempOrigin.Y+((tempXIndex-1)*tempXSpacing*SIN(RAD(-tempAngle)))+((tempYIndex-1)*tempYSpacing*COS(RAD(-tempAngle))));
			tempLocation.X := tempX / 1000;
			tempLocation.Y := tempY / 1000;
			tempLocation.Z := tempOrigin.Z;
			tempLocation.Yaw := tempOrigin.Yaw;
			tempLocation.Pitch := tempOrigin.Pitch;
			tempLocation.Roll := tempOrigin.Roll;
			// copy the temp loc into the appropriate robot location array index
			COP(tempLocation,s800.LocationConfig[tempLocIndex].Coordinate,1);
		End_For;
	End_For;

RET();