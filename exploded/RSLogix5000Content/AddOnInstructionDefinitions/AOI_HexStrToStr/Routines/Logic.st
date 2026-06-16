(* The RFID tag serial number is in a hexidecimal format. The following logic changes the hex  *)
(* number to an ASCII string character. BTDT_High is a FBD_BIT_FIELD_DISTRIBUTE data type used *)
(* by the BTDT command. Refer to the RSLogix program documentation for more information.       *)

(* Convert HexString to String *)
	BTDT_High.SourceBit	:= 4 ;
	BTDT_High.Length 	:= 4 ;
	BTDT_High.DestBit 	:= 0 ;
	BTDT_High.Target 	:= 0 ;

	wrk_idxStr := 0 ;

	for idx := 0 to (In.LEN - 1) do 
		BTDT_High.Source := In.DATA[idx] ;
		BTDT(BTDT_High);
		wrk_highNibble := BTDT_High.Dest ;
		wrk_lowNibble := In.DATA[idx] AND 15 ;

		if wrk_highNibble >= 10 then
			Out.DATA[wrk_idxStr] := wrk_highNibble + 55 ;
		else
			Out.DATA[wrk_idxStr] := wrk_highNibble + 48 ;
		end_if ;
		if wrk_lowNibble >= 10 then
			Out.DATA[wrk_idxStr + 1] := wrk_lowNibble + 55 ;
		else
			Out.DATA[wrk_idxStr + 1] := wrk_lowNibble + 48 ;
		end_if ;
		wrk_idxStr := wrk_idxStr + 2 ;
	end_for ;

	Out.LEN := wrk_idxStr ;
