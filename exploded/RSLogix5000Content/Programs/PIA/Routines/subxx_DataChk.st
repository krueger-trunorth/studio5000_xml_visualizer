SBR(data_good, data_compare);

data_chk_dn := 0;
data_chk_ok := 1;

count :=0;

for count := 0
to (49)
do
data_chk_err_indexes[count] := 0;

end_for;


err_count := 0;


SIZE(data_compare.Value[0], 0, array_size1);
count := 0;
for count := 0 
to (array_size1 - 1) 
do
if  data_compare.Value[count] <> data_good.Value[count] then
data_chk_ok := 0;
data_chk_err_indexes[count] := 1;
err_count := err_count + 1;
end_if;
end_for;



if count <> (array_size1) then
	data_chk_ok := 0;
end_if;

data_chk_dn := 1;

