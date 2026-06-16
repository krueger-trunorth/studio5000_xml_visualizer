SBR(exc_data_good, exc_data_compare);

data_chk_dn := 0;
data_chk_ok := 1;


for count := 0
to (20)
do
data_chk_exc_err_indexes[count] := 0;
end_for;


// Exception description Data


count := 0;
err_count := 0;
size(exc_data_good.Qty,0,elements);

for count := 0
to (elements - 1)
do

if  (exc_data_compare.Qty[count] <> exc_data_good.Qty[count]) or (exc_data_compare.Reject[count] <> exc_data_good.Reject[count])then
data_chk_ok := 0;
data_chk_exc_err_indexes[count] := 1;
err_count := err_count + 1;
end_if;



end_for;


if count <> (elements) then
	data_chk_ok := 0;
end_if;

data_chk_dn := 1;