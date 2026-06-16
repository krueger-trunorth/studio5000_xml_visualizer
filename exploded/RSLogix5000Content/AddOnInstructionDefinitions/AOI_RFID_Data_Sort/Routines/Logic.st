k_semicolon_decimal:=59;
k_less_than_decimal:=60;
k_grt_than_decimal:=62;

if (function=1) then //  Compare the data that was read immediately following the write
	data_error:=0;
	err_code:=0;
	data_read_sort_complete:=0;
	cps(k_blank_rfid_cfg,rfid_data_read_return,1);
	cps(k_blank_element_list[0],element_list[0],100);
	size(rfid_sint_read_array,0,sint_array_size);
	// Count the total number of elements.  If a value exists in the TagID component of the UDT it is considered an item that was required.
	size(rfid_data.Data,0,array_size);
	total_elements:=0;
	array_final_element:=array_size - 1;
	for count1:=0 to (array_final_element) do
		if (rfid_data.TagIDs[count1]<>k_null_string) then
			element_list[total_elements]:=count1;
			total_elements:=total_elements+1;
		end_if;
	end_for;
	// Compare each element of the SINT arrays using the SINT array that was written and the one that was returned as part of the write command.
	for count1:=0 to (sint_array_size-1) do
		if (rfid_sint_read_array[count1]<>rfid_sint_write_array[count1]) then
			data_error:=1;
			err_code:=7;
			exit;
		end_if;
	end_for;
	//  Convert the SINT data array to the RFID_Cfg datatype format and place the data in the correct locations.
	count1:=0;
	for count1:=0 to (total_elements-1) do
		data_end:=0;
		location:=element_list[count1];
		temp_string_start:=rfid_data.Start[location];
		temp_string_length:=rfid_data.Length[location];
		cps(rfid_sint_read_array[temp_string_start],temp_string.DATA[0],temp_string_length);
		temp_string.LEN:=temp_string_length;
		find(temp_string,k_grt_than_string,1,tagid_end);
		temp_tagid.LEN:=tagid_end;
		cps(temp_string.DATA[0],temp_tagid.DATA[0],tagid_end);
		temp_data_length:=rfid_data.Length[location]-tagid_end;
		find(temp_string,k_semi_colon,1,data_end);
		data_end:=data_end-1;
		if (data_end<0) then
			data_error:=1;
			err_code:=5;
		end_if;
		cps(temp_string.DATA[tagid_end],temp_data.DATA[0],data_end);
		data_string_length:=data_end-tagid_end;
		rfid_data_read_return.Start[location]:=rfid_data.Start[location];
		rfid_data_read_return.Length[location]:=rfid_data.Length[location];
		cps(temp_tagid.DATA[0],rfid_data_read_return.TagIDs[location].DATA[0],tagid_end);
		cps(temp_data.DATA[0],rfid_data_read_return.Data[location].DATA[0],data_string_length);
		rfid_data_read_return.Data[location].LEN:=data_end-tagid_end;
		rfid_data_read_return.TagIDs[location].LEN:=tagid_end;
		if (rfid_data_read_return.TagIDs[location]<>rfid_data.TagIDs[location]) then
			data_error:=1;
			err_code:=5;
		end_if;
	end_for;
	//  Set data read sort complete status to 1
	data_read_sort_complete:=1;
end_if;

if function=2 then //  Prepare the data to be written
	err_code:=0;
	cps(k_blank_rfid_cfg,rfid_data_sorted,1);
	cps(k_blank_rfid_cfg,rfid_data_read_return,1);
	cps(k_blank_element_list[0],element_list[0],100);
	size(rfid_data.Data,0,array_size);
	total_elements:=0;
	array_final_element:=array_size-1;
	// Count the total number of elements.  If a value exists in the TagID component of the UDT it is considered an item that was required.
	for count1:=0 to (array_final_element) do
		if (rfid_data.TagIDs[count1]<>k_null_string) then
			element_list[total_elements]:=count1;
			total_elements:=total_elements+1;
		end_if;
	end_for;
	//  Sort the data to be written by the start location to make sure that the data gets written to the proper location on the RFID tag
	//  since the code writes 188 byte blocks in sequence.  The RFID_Cfg tags do NOT need to be set up in sequence.  This logic ensures sequential order.
	count5:=0;
	count1:=0;
	flag:=1;
	while flag do
		count1:=0;
		flag:=0;
		for count1:=0 to (total_elements-2) do
			location:=element_list[count1];
			location2:=element_list[count1+1];
			if (location2<=array_final_element) then
				if (rfid_data.Start[location]>rfid_data.Start[location2]) then
					hold1:=element_list[count1];
					hold2:=element_list[count1+1];
					element_list[count1]:=hold2;
					element_list[count1+1]:=hold1;
					flag:=1;
					exit;
				end_if;
			end_if;
		end_for;
		count5:=count5+1;
	end_while;
	// Place the sorted RFID_Cfg data in a "Sorted" RFID_Cfg temporary tag.
	count1:=0;
	for count1:=0 to (total_elements-1) do
		location:=element_list[count1];
		rfid_data_sorted.Start[count1]:=rfid_data.Start[location];
		rfid_data_sorted.Length[count1]:=rfid_data.Length[location];
		cps(rfid_data.TagIDs[location],rfid_data_sorted.TagIDs[count1],1);
		cps(rfid_data.Data[location],rfid_data_sorted.Data[count1],1);
	end_for;
	//  Check to make sure the start and lengths are valid and do not cause an "overwrite" situation.
	count1:=0;
	bad_data_config:=0;
	for count1:=0 to (total_elements-1) do
		if (count1<total_elements-1) then
			if ((rfid_data_sorted.Start[count1]+rfid_data_sorted.Length[count1])>rfid_data_sorted.Start[count1+1]) then
				bad_data_config:=1;
				err_code:=8;
			end_if;
		end_if;
	end_for;
	//  Add a semi-colon to the end of each item and populate the SINT tag that is used to write to the tag.
	count1:=0;
	cps (k_blank_rfid_cfg.Data[0].DATA[0],concat_string.DATA[0],82);
	for count1:=0 to (total_elements-1) do
		concat(rfid_data_sorted.TagIDs[count1],rfid_data_sorted.Data[count1],concat_string);
		concat(concat_string,k_semi_colon,concat_string);
		sint_start_location:=rfid_data_sorted.Start[count1];
		cps(concat_string.DATA[0],rfid_sint_write_array[sint_start_location],rfid_data_sorted.Length[count1]);
		cps(k_blank_rfid_cfg.Data[0].DATA[0],concat_string.DATA[0],82);
	end_for;
	data_write_sort_complete:=1;
end_if;

if function=3 then //  Compare the data that was read only look for tagID accuracy
	data_error:=0;
	err_code:=0;
	data_read_sort_complete:=0;
	cps(k_blank_rfid_cfg,rfid_data_read_return,1);
	size(rfid_sint_read_array,0,sint_array_size);
	// Count the total number of elements.  If a value exists in the TagID component of the UDT it is considered an item that was required.
	size(rfid_data.Data,0,array_size);
	total_elements:=0;
	array_final_element:=array_size-1;
	for count1:=0 to (array_final_element) do
		if (rfid_data.TagIDs[count1]<>k_null_string) then
			element_list[total_elements]:=count1;
			total_elements:=total_elements + 1;
		end_if;
	end_for;
	//Sort the data to be written by the start location to make sure that the data gets written to the proper location on the RFID tag
	//since the code writes 188 byte blocks in sequence.  The RFID_Cfg tags do NOT need to be set up in sequence.  This logic ensures sequential order.
	count5:=0;
	count1:=0;
	flag:=1;
	while flag do
		count1:=0;
		flag:=0;
		for count1:=0 to (total_elements-2) do
			location:=element_list[count1];
			location2:=element_list[count1+1];
			if (location2<=array_final_element) then
				if (rfid_data.Start[location]>rfid_data.Start[location2]) then
					hold1:=element_list[count1];
					hold2:=element_list[count1+1];
					element_list[count1]:=hold2;
					element_list[count1+1]:=hold1;
					flag:=1;
					exit;
				end_if;
			end_if;
		end_for;
		count5:=count5+1;
	end_while;
	//  Take the data read from the RFID tag and populate it in the RFID_Cfg tag in the properly configured locations.
	count1:=0;
	for count1:=0 to (total_elements-1) do
		data_end:=0;
		location:=element_list[count1];
		temp_string_start:=rfid_data.Start[location];
		temp_string_length:=rfid_data.Length[location];
		cps(rfid_sint_read_array[temp_string_start],temp_string.DATA[0],temp_string_length);
		temp_string.LEN:=temp_string_length;
		find(temp_string,k_grt_than_string,1,tagid_end);
		temp_tagid.LEN:=tagid_end;
		cps(temp_string.DATA[0],temp_tagid.DATA[0],tagid_end);
		temp_data_length:=rfid_data.Length[location]-tagid_end;
		find(temp_string,k_semi_colon,1,data_end);
		data_end:=data_end-1;
		if (data_end<0) then
			data_error:=1;
			err_code:=5;
		end_if;
		cps(temp_string.DATA[tagid_end],temp_data.DATA[0],data_end);
		data_string_length:=data_end-tagid_end;
		rfid_data_read_return.Start[location]:=rfid_data.Start[location];
		rfid_data_read_return.Length[location]:=rfid_data.Length[location];
		cps(temp_tagid.DATA[0],rfid_data_read_return.TagIDs[location].DATA[0],tagid_end);
		cps(temp_data.DATA[0],rfid_data_read_return.Data[location].DATA[0],data_string_length);
		rfid_data_read_return.Data[location].LEN:=data_end-tagid_end;
		rfid_data_read_return.TagIDs[location].LEN:=tagid_end;
		if (rfid_data_read_return.TagIDs[location]<>rfid_data.TagIDs[location]) then
			data_error:=1;
			err_code:=5;
		end_if;
	end_for;
	data_read_sort_complete:=1;
end_if;

if (function=4) then //  Read all data on the tag,parse by "<" as the start and ";" as the end
	data_error:=0;
	err_code:=0;
	data_read_sort_complete:=0;
	cps(k_blank_rfid_cfg,rfid_data_read_return,1);
	element_start_found:=0;
	element_tagID_end_found:=0;
	count1:=0;
	byte_count:=0;
	for byte_count:=0 to (total_bytes-1) do
		if (rfid_sint_read_array[byte_count]=k_less_than_decimal) then
			element_start:=byte_count;
			element_start_found:=1;
		end_if;
		if (element_start_found) then
			if (rfid_sint_read_array[byte_count]=k_semicolon_decimal) then
				element_end_found :=1;
				element_end_loc:=byte_count;
			end_if;
		end_if;
		if (element_start_found and element_end_found) then
			temp_length:=(element_end_loc-element_start);
			cps(rfid_sint_read_array[element_start],rfid_data_entire_read_return[count1].DATA[0],temp_length);
			cps(temp_length,rfid_data_entire_read_return[count1].LEN,1);
			temp_start:=(element_tagID_end_loc+1);
			count1:=count1+1;
			element_start_found:=0;
			element_tagID_end_found:=0;
			element_end_found:=0;
		end_if;
	end_for;
	data_read_sort_complete:=1;
end_if;
