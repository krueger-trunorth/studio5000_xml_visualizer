// T_DIFF : Difference between two Dates  (Date/Time minus Date/Time to get Amount of Time
// 
// This instruction finds the difference between one Date/Time and another (both assumed valid) and reports it as
// an Amount of Time.  The amount of time is given as a number of Days, Hours, Minutes, Seconds and Microseconds:
//
//  NOTE:  This instruction does NOT switch to Julian dates for dates before 1582 (or 1753 or whenever your place of interest
//    switched to the Gregorian Calendar -- see Wikipedia on "Gregorian Calendar" for details)!  This instruction assumes the 
//    Gregorian Calendar extends "indefinitely" (about 5.8 million years) either side of "zero" CE!  It DOES handle the
//    Gregorian 4 / 100 / 400 year rules, so Feb. 29, 2000 is a valid date, but Feb. 29, 2100 is not.  It DOES NOT handle
//    Daylight Savings Time hour offsets when one Date/Time is winter time and the other  is summer time boundaries.  This
//    instruction does not deal with Leap Seconds, and Date/Time parameters MUST be valid Gregorian, normalized Date/Time values:
//
//   *  0 <= Microseconds < 1,000,000
//   *  0 <= Seconds < 60
//   *  0 <= Minutes < 60
//   *  0 <= Hours < 24
//   *  0 <= Days <= 31 and a valid Gregorian Date (Feb = 28 or 29 days, etc.)
//   *  1 <= Month <= 12
//   *  year in the range (about) +/- 5.8 million
//
//  NOTE:  For algorithms used for Gregorian Date and Days Between Dates, see http://alcor.concordia.ca/~gpkatch/gdate-algorithm.html
//
//  Revision 1.0-Example:  2008-Jul-02, DER
//	Release for V17 CD as Date/Time Examples
//

// Add Microseconds
Wrk_Out.uSec := (Ref_DT1.uSec-Ref_DT2.uSec+1000000) MOD 1000000;
// Carry excess Seconds
Wrk_SecFrom_uSec := (Ref_DT1.uSec-Ref_DT2.uSec+1000000) / 1000000 - 1;

// Add Seconds
Wrk_Out.Sec := (Ref_DT1.Sec-Ref_DT2.Sec+Wrk_SecFrom_uSec+60) MOD 60;
// Carry excess Minutes
Wrk_MinFromSec := (Ref_DT1.Sec-Ref_DT2.Sec+Wrk_SecFrom_uSec+60) / 60 - 1;

// Add Minutes
Wrk_Out.Min := (Ref_DT1.Min-Ref_DT2.Min+Wrk_MinFromSec+60) MOD 60;
// Carry excess Hours
Wrk_HrFromMin := (Ref_DT1.Min-Ref_DT2.Min+Wrk_MinFromSec+60) / 60 - 1;

// Add Hours
Wrk_Out.Hr := (Ref_DT1.Hr-Ref_DT2.Hr+Wrk_HrFromMin+24) MOD 24;
// Carry excess Days
Wrk_DaFromHr := (Ref_DT1.Hr-Ref_DT2.Hr+Wrk_HrFromMin+24) / 24 - 1;

// That takes care of the time.  To add the days, we need to compute a Gregorian Day Number from the input Date,
// then add the days and compute a Date from the new total Gregorian Day Number.  This takes care of the days in the months.
// (After thet, we'll add the Months and Years like we did with the time.)

// Compute the Gregorian Day Number for the input Date
Wrk_F1 := (Ref_DT1.Mo+9) MOD 12;
Wrk_G1 := Ref_DT1.Yr - Wrk_F1/10;
Wrk_GD1 := 365*Wrk_G1+Wrk_G1/4-Wrk_G1/100+Wrk_G1/400+(Wrk_F1*306+5)/10+Ref_DT1.Da-1;

Wrk_F2 := (Ref_DT2.Mo+9) MOD 12;
Wrk_G2 := Ref_DT2.Yr - Wrk_F2/10;
Wrk_GD2 := 365*Wrk_G2+Wrk_G2/4-Wrk_G2/100+Wrk_G2/400+(Wrk_F2*306+5)/10+Ref_DT2.Da-1;

Wrk_Out.Da := Wrk_GD1 - Wrk_GD2 + Wrk_DaFromHr;

// If the number of Days is negative, we need to bump it up by one and subtract 23 hours 59 minutes
//  59 seconds 1,000,000 microseconds (same amount of time) to make result look right...
//  Otherwise instead of -1 uSec we get -1 day +23 hours +59 minutes +59 seconds +999,999 microseconds

If ( Wrk_Out.Da < 0 ) then
	Wrk_Out.Da := Wrk_Out.Da + 1;
	Wrk_Out.Hr := Wrk_Out.Hr - 23;
	Wrk_Out.Min := Wrk_Out.Min - 59;
	Wrk_Out.Sec := Wrk_Out.Sec - 59;
	Wrk_Out.uSec := Wrk_Out.uSec - 1000000;
	If ( Wrk_Out.uSec = -1000000 ) then
		Wrk_Out.uSec := 0;
		Wrk_Out.Sec := Wrk_Out.Sec - 1;
	End_If;
	If ( Wrk_Out.Sec = -60 ) then
		Wrk_Out.Sec := 0;
		Wrk_Out.Min := Wrk_Out.Min - 1;
	End_If;
	If ( Wrk_Out.Min = -60 ) then
		Wrk_Out.Min := 0;
		Wrk_Out.Hr := Wrk_Out.Hr - 1;
	End_If;
	If ( Wrk_Out.Hr = -24 ) then
		Wrk_Out.Hr := 0;
		Wrk_Out.Da := Wrk_Out.Da - 1;
	End_If;
End_If;

// Copy the final numbers to the Output tag

Ref_Out.Da := Wrk_Out.Da;
Ref_Out.Hr := Wrk_Out.Hr;
Ref_Out.Min := Wrk_Out.Min;
Ref_Out.Sec := Wrk_Out.Sec;
Ref_Out.uSec := Wrk_Out.uSec;

// No Months
Ref_Out.Mo := 0;
// No Years
Ref_Out.Yr := 0;
