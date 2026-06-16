// T_ADD : Add Date/Time plus Time to get new Date/Time
// 
// This instruction adds a given amount of Time to a Date/Time to arrive at a new Date/Time
// The new Date/Time is "normalized", that is, given as a valid (if possible) Gregorian Date and Time:
//
//   *  0 <= Microseconds < 1,000,000
//   *  0 <= Seconds < 60    (NOTE: this instruction cannot add leap seconds;  sorry!
//   *  0 <= Minutes < 60
//   *  0 <= Hours < 24
//   *  1 <= Day <= 31 AND Date is a Valid Gregorian Date (see below)
//   *  1 <= Month <= 12
//
//  NOTE:  This instruction does NOT switch to Julian dates for dates before 1582 (or 1753 or whenever your place of interest
//    switched to the Gregorian Calendar -- see Wikipedia on "Gregorian Calendar" for details)!  This instruction assumes the 
//    Gregorian Calendar extends "indefinitely" (about 5.8 million years) either side of "zero" CE!  It DOES handle the
//    Gregorian 4 / 100 / 400 year rules, so Feb. 29, 2000 is a valid date, but Feb. 29, 2100 is not.  It DOES NOT handle
//    Daylight Savings Time hour offsets when the amount of Time added carries the Date/Time across summer/winter time boundaries.
//
//  NOTE:  For algorithms used for Gregorian Date and Days Between Dates, see http://alcor.concordia.ca/~gpkatch/gdate-algorithm.html
//
//  Revision 1.0-Example:  2008-Jul-02, DER
//	Release for V17 CD as Date/Time Examples
//

// Add Microseconds (accounting for adding a negative number of Microseconds!)
Ref_Out.uSec := (Ref_DT.uSec+Ref_Time.uSec) MOD 1000000;
// Carry excess Seconds
Wrk_SecFrom_uSec := (Ref_DT.uSec+Ref_Time.uSec) / 1000000;
IF (Ref_Out.uSec < 0) THEN
  Ref_Out.uSec := Ref_Out.uSec + 1000000;
  Wrk_SecFrom_uSec := Wrk_SecFrom_uSec - 1;
END_IF;

// Add Seconds
Ref_Out.Sec := (Ref_DT.Sec+Ref_Time.Sec+Wrk_SecFrom_uSec) MOD 60;
// Carry excess Minutes
Wrk_MinFromSec := (Ref_DT.Sec+Ref_Time.Sec+Wrk_SecFrom_uSec) / 60;
// Handle negative sum
IF (Ref_Out.Sec < 0) THEN
  Ref_Out.Sec := Ref_Out.Sec + 60;
  Wrk_MinFromSec := Wrk_MinFromSec - 1;
END_IF;

// Add Minutes
Ref_Out.Min := (Ref_DT.Min+Ref_Time.Min+Wrk_MinFromSec) MOD 60;
// Carry excess Hours
Wrk_HrFromMin := (Ref_DT.Min+Ref_Time.Min+Wrk_MinFromSec) / 60;
// Handle negative sum
IF (Ref_Out.Min < 0) THEN
  Ref_Out.Min := Ref_Out.Min + 60;
  Wrk_HrFromMin := Wrk_HrFromMin - 1;
END_IF;

// Add Hours
Ref_Out.Hr := (Ref_DT.Hr+Ref_Time.Hr+Wrk_HrFromMin) MOD 24;
// Carry excess Days
Wrk_DaFromHr := (Ref_DT.Hr+Ref_Time.Hr+Wrk_HrFromMin) / 24;
// Handle negative sum
IF (Ref_Out.Hr < 0) THEN
  Ref_Out.Hr := Ref_Out.Hr + 24;
  Wrk_DaFromHr := Wrk_DaFromHr - 1;
END_IF;

// That takes care of the time.  To add the days, we need to compute a Gregorian Day Number from the input Date,
// then add the days and compute a Date from the new total Gregorian Day Number.  This takes care of the days in the months.
// (After thet, we'll add the Months and Years like we did with the time.)

// Compute the Gregorian Day Number for the input Date
Wrk_F := (Ref_DT.Mo+9) MOD 12;
Wrk_G := Ref_DT.Yr - Wrk_F/10;
Wrk_GD := 365*Wrk_G+Wrk_G/4-Wrk_G/100+Wrk_G/400+(Wrk_F*306+5)/10+Ref_DT.Da-1;

// Add the days
Wrk_GD := Wrk_GD+Ref_Time.Da+Wrk_DaFromHr;

// And back out from this Gregorian Day Number to a date
Wrk_yyy := TRUNC (Wrk_GD +1.5)/365.2425;
Wrk_ddd := Wrk_GD - (365*Wrk_yyy+Wrk_yyy/4-Wrk_yyy/100+Wrk_yyy/400);
IF (Wrk_ddd < 0) THEN
	Wrk_yyy := Wrk_yyy - 1;
	Wrk_ddd := Wrk_GD - (365*Wrk_yyy+Wrk_yyy/4-Wrk_yyy/100+Wrk_yyy/400);
	IF (Wrk_ddd < 0) THEN
		Wrk_yyy := Wrk_yyy - 1;
		Wrk_ddd := Wrk_GD - (365*Wrk_yyy+Wrk_yyy/4-Wrk_yyy/100+Wrk_yyy/400);
	END_IF;
END_IF;
Wrk_mmm := (100*Wrk_ddd + 52)/3060;
Wrk_y := Wrk_yyy + (Wrk_mmm + 2)/12;
Wrk_m := ((Wrk_mmm + 2) MOD 12) + 1; 
Ref_Out.Da := Wrk_ddd - ((Wrk_mmm * 306) + 5)/10 + 1;

// Add Months
Ref_Out.Mo := ((Wrk_m+Ref_Time.Mo-1) MOD 12)+1;
// Carry excess Years
Wrk_YrFromMo := (Wrk_m+Ref_Time.Mo-1) / 12;
// Handle negative sum
IF (Ref_Out.Mo < 1) THEN
  Ref_Out.Mo := Ref_Out.Mo + 12;
  Wrk_YrFromMo := Wrk_YrFromMo - 1;
END_IF;

// Add Years
Ref_Out.Yr := Wrk_y+Ref_Time.Yr+Wrk_YrFromMo;
