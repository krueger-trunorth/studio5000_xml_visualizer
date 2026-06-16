SBR(trav_good, trav_compare, trav_qty_good, trav_qty_compare);


trav_chk_dn := 0;
trav_chk_ok := 1;

count :=0;

for count := 0
to (trav_number_array_size)
do
trav_chk_err_indexes[count] := 0;

end_for;


err_count := 0;


SIZE(trav_compare[0], 0, array_size1);
count := 0;
for count := 0 
to (array_size1 - 1) 
do
if  (trav_compare[count] <> trav_good[count]) then
trav_chk_ok := 0;
trav_chk_err_indexes[count] := 1;
err_count := err_count + 1;
end_if;
end_for;



if trav_qty_good <> trav_qty_compare then
	trav_chk_ok := 0;
end_if;

trav_chk_dn := 1;