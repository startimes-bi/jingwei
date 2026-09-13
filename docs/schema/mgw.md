# MGW schema snapshot

## 探索边界

- 用户指定范围：BIAI → wangzp → stage → mgw。
- 数据库确认：本次仅查询当前授权 schema 的 information_schema 元数据。
- 检查时间（UTC）：2026-09-13T03:26:02+00:00
- 数据库确认：基础表数量 17；本次记录的授权表数量 17。
- Schema fingerprint（SHA-256，基于表/字段/索引/外键元数据）：bfa52b87c762f9c30018e5923d1bb7f172de76e5257469d97225d337af587f92
- 本文件不包含连接地址、用户名、密码、Token、业务数据、样本值、查询日志或导出文件。

## 表清单

| 表名 | 类型 |
| --- | --- |
| metric_sub_count | BASE TABLE |
| metric_sub_deduction_arppu | BASE TABLE |
| metric_sub_deduction_arpu | BASE TABLE |
| metric_sub_deduction_count | BASE TABLE |
| metric_sub_deduction_count_month_distinct | BASE TABLE |
| metric_sub_deduction_money | BASE TABLE |
| metric_sub_new_count | BASE TABLE |
| metric_sub_new_count_v2 | BASE TABLE |
| metric_sub_online_count | BASE TABLE |
| metric_sub_online_count_month_distinct | BASE TABLE |
| metric_sub_online_rate | BASE TABLE |
| metric_sub_recharge_arppu | BASE TABLE |
| metric_sub_recharge_count | BASE TABLE |
| metric_sub_recharge_count_month_distinct | BASE TABLE |
| metric_sub_recharge_money | BASE TABLE |
| metric_tv_sale | BASE TABLE |
| metric_tv_sale_v2 | BASE TABLE |

## 字段清单

### metric_sub_count

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | package_class | varchar(30) | YES |
| 9 | wct_flag | tinyint(1) | YES |
| 10 | rate_flag | varchar(30) | YES |
| 11 | tv_class | varchar(30) | YES |
| 12 | sub_count | int | YES |
| 13 | data_source | tinyint | NO |

### metric_sub_deduction_arppu

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | package_class | varchar(30) | YES |
| 9 | wct_flag | tinyint(1) | YES |
| 10 | rate_flag | varchar(30) | YES |
| 11 | tv_class | varchar(30) | YES |
| 12 | deduction_arppu | double(10,3) | YES |
| 13 | data_source | tinyint | NO |

### metric_sub_deduction_arpu

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | load_month | char(6) | NO |
| 3 | business | varchar(30) | NO |
| 4 | company_region_id | int | YES |
| 5 | company_id | int | YES |
| 6 | region_id | int | YES |
| 7 | sale_area_id | int | YES |
| 8 | fta_flag | tinyint(1) | YES |
| 9 | package_class | varchar(30) | YES |
| 10 | wct_flag | tinyint(1) | YES |
| 11 | rate_flag | varchar(30) | YES |
| 12 | tv_class | varchar(30) | YES |
| 13 | deduction_arpu | double(10,3) | YES |
| 14 | data_source | tinyint | NO |

### metric_sub_deduction_count

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | package_class | varchar(30) | YES |
| 9 | wct_flag | tinyint(1) | YES |
| 10 | rate_flag | varchar(30) | YES |
| 11 | sub_deduction_count | int | YES |
| 12 | data_source | tinyint | NO |
| 13 | active_label | int | YES |

### metric_sub_deduction_count_month_distinct

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | package_class | varchar(30) | YES |
| 8 | wct_flag | tinyint(1) | YES |
| 9 | rate_flag | varchar(30) | YES |
| 10 | sub_deduction_count | int | YES |
| 11 | data_source | tinyint | NO |

### metric_sub_deduction_money

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | package_class | varchar(30) | YES |
| 9 | wct_flag | tinyint(1) | YES |
| 10 | rate_flag | varchar(30) | YES |
| 11 | tv_class | varchar(30) | YES |
| 12 | deduction_money | double(10,2) | YES |
| 13 | data_source | tinyint | NO |
| 14 | load_month | char(6) | YES |
| 15 | active_label | int | YES |

### metric_sub_new_count

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | wct_flag | tinyint(1) | YES |
| 9 | package_class | varchar(30) | YES |
| 10 | tv_class | varchar(30) | YES |
| 11 | sub_day_new_count | int | YES |
| 12 | sub_month_new_count | int | YES |
| 13 | sub_year_new_count | int | YES |
| 14 | data_source | tinyint | NO |

### metric_sub_new_count_v2

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | wct_flag | tinyint(1) | YES |
| 9 | package_class | varchar(30) | YES |
| 10 | tv_class | varchar(30) | YES |
| 11 | sub_day_new_count | int | YES |
| 12 | sub_month_new_count | int | YES |
| 13 | sub_year_new_count | int | YES |
| 14 | data_source | tinyint | NO |

### metric_sub_online_count

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | package_class | varchar(30) | YES |
| 9 | wct_flag | tinyint(1) | YES |
| 10 | rate_flag | varchar(30) | YES |
| 11 | tv_class | varchar(30) | YES |
| 12 | online_count | int | YES |
| 13 | data_source | tinyint | NO |

### metric_sub_online_count_month_distinct

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | package_class | varchar(30) | YES |
| 8 | wct_flag | tinyint(1) | YES |
| 9 | rate_flag | varchar(30) | YES |
| 10 | online_count | int | YES |
| 11 | data_source | tinyint | NO |

### metric_sub_online_rate

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | package_class | varchar(30) | YES |
| 9 | wct_flag | tinyint(1) | YES |
| 10 | rate_flag | varchar(30) | YES |
| 11 | tv_class | varchar(30) | YES |
| 12 | online_rate | double(10,4) | YES |
| 13 | data_source | tinyint | NO |

### metric_sub_recharge_arppu

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | package_class | varchar(30) | YES |
| 8 | wct_flag | tinyint(1) | YES |
| 9 | rate_flag | varchar(30) | YES |
| 10 | tv_class | varchar(30) | YES |
| 11 | recharge_arppu | double(10,3) | YES |
| 12 | data_source | tinyint | NO |

### metric_sub_recharge_count

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | fta_flag | tinyint(1) | YES |
| 8 | package_class | varchar(30) | YES |
| 9 | wct_flag | tinyint(1) | YES |
| 10 | rate_flag | varchar(30) | YES |
| 11 | sub_recharge_count | int | YES |
| 12 | data_source | tinyint | NO |
| 13 | active_label | int | YES |

### metric_sub_recharge_count_month_distinct

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | package_class | varchar(30) | YES |
| 8 | wct_flag | tinyint(1) | YES |
| 9 | rate_flag | varchar(30) | YES |
| 10 | sub_recharge_count | int | YES |
| 11 | data_source | tinyint | NO |

### metric_sub_recharge_money

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | business | varchar(30) | NO |
| 3 | company_region_id | int | YES |
| 4 | company_id | int | YES |
| 5 | region_id | int | YES |
| 6 | sale_area_id | int | YES |
| 7 | package_class | varchar(30) | YES |
| 8 | wct_flag | tinyint(1) | YES |
| 9 | rate_flag | varchar(30) | YES |
| 10 | tv_class | varchar(30) | YES |
| 11 | recharge_money | double(10,2) | YES |
| 12 | data_source | tinyint | NO |
| 13 | load_month | char(6) | YES |
| 14 | active_label | int | YES |

### metric_tv_sale

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | company_region_id | int | YES |
| 3 | company_id | int | YES |
| 4 | region_id | int | YES |
| 5 | sale_area_id | int | YES |
| 6 | tv_class | varchar(30) | YES |
| 7 | digital_flag | varchar(30) | YES |
| 8 | digital_tv_class | varchar(30) | YES |
| 9 | day_sale_count | int | YES |
| 10 | month_sale_count | int | YES |
| 11 | year_sale_count | int | YES |
| 12 | total_sale_count | int | YES |
| 13 | data_source | tinyint | NO |

### metric_tv_sale_v2

| 序号 | 字段 | 数据类型 | 可为空 |
| ---: | --- | --- | --- |
| 1 | load_date | char(8) | NO |
| 2 | load_month | char(6) | NO |
| 3 | load_year | char(6) | NO |
| 4 | company_region_id | int | YES |
| 5 | company_id | int | YES |
| 6 | region_id | int | YES |
| 7 | sale_area_id | int | YES |
| 8 | tv_class | varchar(30) | YES |
| 9 | transaction | varchar(30) | YES |
| 10 | day_sale_count | int | YES |
| 11 | data_source | tinyint | NO |

## 索引关系

| 表名 | 索引名 | 唯一 | 序号 | 字段 | 索引类型 |
| --- | --- | ---: | ---: | --- | --- |
| metric_sub_count | key1 | 否 | 1 | business | BTREE |
| metric_sub_count | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_count | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_count | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_count | key1 | 否 | 5 | fta_flag | BTREE |
| metric_sub_count | key1 | 否 | 6 | package_class | BTREE |
| metric_sub_count | key1 | 否 | 7 | wct_flag | BTREE |
| metric_sub_count | key1 | 否 | 8 | rate_flag | BTREE |
| metric_sub_count | key1 | 否 | 9 | tv_class | BTREE |
| metric_sub_count | key1 | 否 | 10 | load_date | BTREE |
| metric_sub_count | key2 | 否 | 1 | business | BTREE |
| metric_sub_count | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_count | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_count | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_count | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_count | key2 | 否 | 6 | fta_flag | BTREE |
| metric_sub_count | key2 | 否 | 7 | package_class | BTREE |
| metric_sub_count | key2 | 否 | 8 | wct_flag | BTREE |
| metric_sub_count | key2 | 否 | 9 | tv_class | BTREE |
| metric_sub_count | key2 | 否 | 10 | rate_flag | BTREE |
| metric_sub_count | key2 | 否 | 11 | load_date | BTREE |
| metric_sub_count | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 1 | business | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 5 | fta_flag | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 6 | package_class | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 7 | wct_flag | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 8 | rate_flag | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 9 | tv_class | BTREE |
| metric_sub_deduction_arppu | key1 | 否 | 10 | load_date | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 1 | business | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 6 | fta_flag | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 7 | package_class | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 8 | wct_flag | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 9 | rate_flag | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 10 | tv_class | BTREE |
| metric_sub_deduction_arppu | key2 | 否 | 11 | load_date | BTREE |
| metric_sub_deduction_arppu | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 1 | business | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 5 | fta_flag | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 6 | package_class | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 7 | wct_flag | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 8 | rate_flag | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 9 | tv_class | BTREE |
| metric_sub_deduction_arpu | key1 | 否 | 10 | load_date | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 1 | business | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 6 | fta_flag | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 7 | package_class | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 8 | wct_flag | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 9 | rate_flag | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 10 | tv_class | BTREE |
| metric_sub_deduction_arpu | key2 | 否 | 11 | load_date | BTREE |
| metric_sub_deduction_arpu | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 1 | business | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 2 | load_date | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 3 | region_id | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 5 | package_class | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 6 | fta_flag | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 7 | wct_flag | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 8 | rate_flag | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 9 | tv_class | BTREE |
| metric_sub_deduction_arpu | key4 | 否 | 10 | company_id | BTREE |
| metric_sub_deduction_count | key1 | 否 | 1 | business | BTREE |
| metric_sub_deduction_count | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_deduction_count | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_deduction_count | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_deduction_count | key1 | 否 | 5 | fta_flag | BTREE |
| metric_sub_deduction_count | key1 | 否 | 6 | package_class | BTREE |
| metric_sub_deduction_count | key1 | 否 | 7 | wct_flag | BTREE |
| metric_sub_deduction_count | key1 | 否 | 8 | rate_flag | BTREE |
| metric_sub_deduction_count | key1 | 否 | 9 | load_date | BTREE |
| metric_sub_deduction_count | key2 | 否 | 1 | business | BTREE |
| metric_sub_deduction_count | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_deduction_count | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_deduction_count | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_deduction_count | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_deduction_count | key2 | 否 | 6 | fta_flag | BTREE |
| metric_sub_deduction_count | key2 | 否 | 7 | package_class | BTREE |
| metric_sub_deduction_count | key2 | 否 | 8 | wct_flag | BTREE |
| metric_sub_deduction_count | key2 | 否 | 9 | rate_flag | BTREE |
| metric_sub_deduction_count | key2 | 否 | 10 | load_date | BTREE |
| metric_sub_deduction_count | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_deduction_count_month_distinct | key1 | 否 | 1 | business | BTREE |
| metric_sub_deduction_count_month_distinct | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_deduction_count_month_distinct | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_deduction_count_month_distinct | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_deduction_count_month_distinct | key1 | 否 | 5 | package_class | BTREE |
| metric_sub_deduction_count_month_distinct | key1 | 否 | 6 | wct_flag | BTREE |
| metric_sub_deduction_count_month_distinct | key1 | 否 | 7 | rate_flag | BTREE |
| metric_sub_deduction_count_month_distinct | key1 | 否 | 8 | load_date | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 1 | business | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 6 | package_class | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 7 | wct_flag | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 8 | rate_flag | BTREE |
| metric_sub_deduction_count_month_distinct | key2 | 否 | 9 | load_date | BTREE |
| metric_sub_deduction_count_month_distinct | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_deduction_money | key1 | 否 | 1 | business | BTREE |
| metric_sub_deduction_money | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_deduction_money | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_deduction_money | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_deduction_money | key1 | 否 | 5 | fta_flag | BTREE |
| metric_sub_deduction_money | key1 | 否 | 6 | package_class | BTREE |
| metric_sub_deduction_money | key1 | 否 | 7 | wct_flag | BTREE |
| metric_sub_deduction_money | key1 | 否 | 8 | rate_flag | BTREE |
| metric_sub_deduction_money | key1 | 否 | 9 | tv_class | BTREE |
| metric_sub_deduction_money | key1 | 否 | 10 | load_date | BTREE |
| metric_sub_deduction_money | key2 | 否 | 1 | business | BTREE |
| metric_sub_deduction_money | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_deduction_money | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_deduction_money | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_deduction_money | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_deduction_money | key2 | 否 | 6 | fta_flag | BTREE |
| metric_sub_deduction_money | key2 | 否 | 7 | package_class | BTREE |
| metric_sub_deduction_money | key2 | 否 | 8 | wct_flag | BTREE |
| metric_sub_deduction_money | key2 | 否 | 9 | rate_flag | BTREE |
| metric_sub_deduction_money | key2 | 否 | 10 | tv_class | BTREE |
| metric_sub_deduction_money | key2 | 否 | 11 | load_date | BTREE |
| metric_sub_deduction_money | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_new_count | key1 | 否 | 1 | business | BTREE |
| metric_sub_new_count | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_new_count | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_new_count | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_new_count | key1 | 否 | 5 | package_class | BTREE |
| metric_sub_new_count | key1 | 否 | 6 | tv_class | BTREE |
| metric_sub_new_count | key1 | 否 | 7 | fta_flag | BTREE |
| metric_sub_new_count | key1 | 否 | 8 | wct_flag | BTREE |
| metric_sub_new_count | key1 | 否 | 9 | load_date | BTREE |
| metric_sub_new_count | key2 | 否 | 1 | business | BTREE |
| metric_sub_new_count | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_new_count | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_new_count | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_new_count | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_new_count | key2 | 否 | 6 | package_class | BTREE |
| metric_sub_new_count | key2 | 否 | 7 | tv_class | BTREE |
| metric_sub_new_count | key2 | 否 | 8 | fta_flag | BTREE |
| metric_sub_new_count | key2 | 否 | 9 | wct_flag | BTREE |
| metric_sub_new_count | key2 | 否 | 10 | load_date | BTREE |
| metric_sub_new_count | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 1 | business | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 5 | package_class | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 6 | tv_class | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 7 | fta_flag | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 8 | wct_flag | BTREE |
| metric_sub_new_count_v2 | key1 | 否 | 9 | load_date | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 1 | business | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 6 | package_class | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 7 | tv_class | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 8 | fta_flag | BTREE |
| metric_sub_new_count_v2 | key2 | 否 | 9 | wct_flag | BTREE |
| metric_sub_new_count_v2 | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_online_count | key1 | 否 | 1 | business | BTREE |
| metric_sub_online_count | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_online_count | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_online_count | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_online_count | key1 | 否 | 5 | fta_flag | BTREE |
| metric_sub_online_count | key1 | 否 | 6 | package_class | BTREE |
| metric_sub_online_count | key1 | 否 | 7 | wct_flag | BTREE |
| metric_sub_online_count | key1 | 否 | 8 | rate_flag | BTREE |
| metric_sub_online_count | key1 | 否 | 9 | tv_class | BTREE |
| metric_sub_online_count | key1 | 否 | 10 | load_date | BTREE |
| metric_sub_online_count | key2 | 否 | 1 | business | BTREE |
| metric_sub_online_count | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_online_count | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_online_count | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_online_count | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_online_count | key2 | 否 | 6 | fta_flag | BTREE |
| metric_sub_online_count | key2 | 否 | 7 | package_class | BTREE |
| metric_sub_online_count | key2 | 否 | 8 | wct_flag | BTREE |
| metric_sub_online_count | key2 | 否 | 9 | tv_class | BTREE |
| metric_sub_online_count | key2 | 否 | 10 | rate_flag | BTREE |
| metric_sub_online_count | key2 | 否 | 11 | load_date | BTREE |
| metric_sub_online_count | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_online_count_month_distinct | key1 | 否 | 1 | business | BTREE |
| metric_sub_online_count_month_distinct | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_online_count_month_distinct | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_online_count_month_distinct | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_online_count_month_distinct | key1 | 否 | 5 | package_class | BTREE |
| metric_sub_online_count_month_distinct | key1 | 否 | 6 | wct_flag | BTREE |
| metric_sub_online_count_month_distinct | key1 | 否 | 7 | rate_flag | BTREE |
| metric_sub_online_count_month_distinct | key1 | 否 | 8 | load_date | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 1 | business | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 6 | package_class | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 7 | wct_flag | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 8 | rate_flag | BTREE |
| metric_sub_online_count_month_distinct | key2 | 否 | 9 | load_date | BTREE |
| metric_sub_online_count_month_distinct | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_online_rate | key1 | 否 | 1 | business | BTREE |
| metric_sub_online_rate | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_online_rate | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_online_rate | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_online_rate | key1 | 否 | 5 | fta_flag | BTREE |
| metric_sub_online_rate | key1 | 否 | 6 | package_class | BTREE |
| metric_sub_online_rate | key1 | 否 | 7 | wct_flag | BTREE |
| metric_sub_online_rate | key1 | 否 | 8 | rate_flag | BTREE |
| metric_sub_online_rate | key1 | 否 | 9 | tv_class | BTREE |
| metric_sub_online_rate | key1 | 否 | 10 | load_date | BTREE |
| metric_sub_online_rate | key2 | 否 | 1 | business | BTREE |
| metric_sub_online_rate | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_online_rate | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_online_rate | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_online_rate | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_online_rate | key2 | 否 | 6 | fta_flag | BTREE |
| metric_sub_online_rate | key2 | 否 | 7 | package_class | BTREE |
| metric_sub_online_rate | key2 | 否 | 8 | wct_flag | BTREE |
| metric_sub_online_rate | key2 | 否 | 9 | tv_class | BTREE |
| metric_sub_online_rate | key2 | 否 | 10 | rate_flag | BTREE |
| metric_sub_online_rate | key2 | 否 | 11 | load_date | BTREE |
| metric_sub_online_rate | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 1 | business | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 5 | package_class | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 6 | wct_flag | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 7 | rate_flag | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 8 | tv_class | BTREE |
| metric_sub_recharge_arppu | key1 | 否 | 9 | load_date | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 1 | business | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 6 | package_class | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 7 | wct_flag | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 8 | rate_flag | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 9 | tv_class | BTREE |
| metric_sub_recharge_arppu | key2 | 否 | 10 | load_date | BTREE |
| metric_sub_recharge_arppu | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_recharge_count | key1 | 否 | 1 | business | BTREE |
| metric_sub_recharge_count | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_recharge_count | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_recharge_count | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_recharge_count | key1 | 否 | 5 | fta_flag | BTREE |
| metric_sub_recharge_count | key1 | 否 | 6 | package_class | BTREE |
| metric_sub_recharge_count | key1 | 否 | 7 | wct_flag | BTREE |
| metric_sub_recharge_count | key1 | 否 | 8 | rate_flag | BTREE |
| metric_sub_recharge_count | key1 | 否 | 9 | load_date | BTREE |
| metric_sub_recharge_count | key2 | 否 | 1 | business | BTREE |
| metric_sub_recharge_count | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_recharge_count | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_recharge_count | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_recharge_count | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_recharge_count | key2 | 否 | 6 | fta_flag | BTREE |
| metric_sub_recharge_count | key2 | 否 | 7 | package_class | BTREE |
| metric_sub_recharge_count | key2 | 否 | 8 | wct_flag | BTREE |
| metric_sub_recharge_count | key2 | 否 | 9 | rate_flag | BTREE |
| metric_sub_recharge_count | key2 | 否 | 10 | load_date | BTREE |
| metric_sub_recharge_count | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_recharge_count_month_distinct | key1 | 否 | 1 | business | BTREE |
| metric_sub_recharge_count_month_distinct | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_recharge_count_month_distinct | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_recharge_count_month_distinct | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_recharge_count_month_distinct | key1 | 否 | 5 | package_class | BTREE |
| metric_sub_recharge_count_month_distinct | key1 | 否 | 6 | wct_flag | BTREE |
| metric_sub_recharge_count_month_distinct | key1 | 否 | 7 | rate_flag | BTREE |
| metric_sub_recharge_count_month_distinct | key1 | 否 | 8 | load_date | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 1 | business | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 6 | package_class | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 7 | wct_flag | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 8 | rate_flag | BTREE |
| metric_sub_recharge_count_month_distinct | key2 | 否 | 9 | load_date | BTREE |
| metric_sub_recharge_count_month_distinct | key3 | 否 | 1 | load_date | BTREE |
| metric_sub_recharge_money | key1 | 否 | 1 | business | BTREE |
| metric_sub_recharge_money | key1 | 否 | 2 | company_id | BTREE |
| metric_sub_recharge_money | key1 | 否 | 3 | region_id | BTREE |
| metric_sub_recharge_money | key1 | 否 | 4 | sale_area_id | BTREE |
| metric_sub_recharge_money | key1 | 否 | 5 | package_class | BTREE |
| metric_sub_recharge_money | key1 | 否 | 6 | wct_flag | BTREE |
| metric_sub_recharge_money | key1 | 否 | 7 | rate_flag | BTREE |
| metric_sub_recharge_money | key1 | 否 | 8 | tv_class | BTREE |
| metric_sub_recharge_money | key1 | 否 | 9 | load_date | BTREE |
| metric_sub_recharge_money | key2 | 否 | 1 | business | BTREE |
| metric_sub_recharge_money | key2 | 否 | 2 | company_region_id | BTREE |
| metric_sub_recharge_money | key2 | 否 | 3 | company_id | BTREE |
| metric_sub_recharge_money | key2 | 否 | 4 | region_id | BTREE |
| metric_sub_recharge_money | key2 | 否 | 5 | sale_area_id | BTREE |
| metric_sub_recharge_money | key2 | 否 | 6 | package_class | BTREE |
| metric_sub_recharge_money | key2 | 否 | 7 | wct_flag | BTREE |
| metric_sub_recharge_money | key2 | 否 | 8 | rate_flag | BTREE |
| metric_sub_recharge_money | key2 | 否 | 9 | tv_class | BTREE |
| metric_sub_recharge_money | key2 | 否 | 10 | load_date | BTREE |
| metric_sub_recharge_money | key3 | 否 | 1 | load_date | BTREE |
| metric_tv_sale | key1 | 否 | 1 | company_id | BTREE |
| metric_tv_sale | key1 | 否 | 2 | region_id | BTREE |
| metric_tv_sale | key1 | 否 | 3 | sale_area_id | BTREE |
| metric_tv_sale | key1 | 否 | 4 | tv_class | BTREE |
| metric_tv_sale | key1 | 否 | 5 | digital_flag | BTREE |
| metric_tv_sale | key1 | 否 | 6 | load_date | BTREE |
| metric_tv_sale | key2 | 否 | 1 | company_region_id | BTREE |
| metric_tv_sale | key2 | 否 | 2 | company_id | BTREE |
| metric_tv_sale | key2 | 否 | 3 | region_id | BTREE |
| metric_tv_sale | key2 | 否 | 4 | sale_area_id | BTREE |
| metric_tv_sale | key2 | 否 | 5 | tv_class | BTREE |
| metric_tv_sale | key2 | 否 | 6 | digital_flag | BTREE |
| metric_tv_sale | key2 | 否 | 7 | load_date | BTREE |
| metric_tv_sale | key3 | 否 | 1 | load_date | BTREE |
| metric_tv_sale | key4 | 否 | 1 | company_id | BTREE |
| metric_tv_sale | key4 | 否 | 2 | region_id | BTREE |
| metric_tv_sale | key4 | 否 | 3 | sale_area_id | BTREE |
| metric_tv_sale | key4 | 否 | 4 | digital_tv_class | BTREE |
| metric_tv_sale | key4 | 否 | 5 | load_date | BTREE |
| metric_tv_sale | key5 | 否 | 1 | company_region_id | BTREE |
| metric_tv_sale | key5 | 否 | 2 | company_id | BTREE |
| metric_tv_sale | key5 | 否 | 3 | region_id | BTREE |
| metric_tv_sale | key5 | 否 | 4 | sale_area_id | BTREE |
| metric_tv_sale | key5 | 否 | 5 | digital_tv_class | BTREE |
| metric_tv_sale | key5 | 否 | 6 | load_date | BTREE |
| metric_tv_sale_v2 | key1 | 否 | 1 | company_id | BTREE |
| metric_tv_sale_v2 | key1 | 否 | 2 | region_id | BTREE |
| metric_tv_sale_v2 | key1 | 否 | 3 | sale_area_id | BTREE |
| metric_tv_sale_v2 | key1 | 否 | 4 | transaction | BTREE |
| metric_tv_sale_v2 | key1 | 否 | 5 | tv_class | BTREE |
| metric_tv_sale_v2 | key1 | 否 | 6 | load_date | BTREE |
| metric_tv_sale_v2 | key2 | 否 | 1 | company_region_id | BTREE |
| metric_tv_sale_v2 | key2 | 否 | 2 | company_id | BTREE |
| metric_tv_sale_v2 | key2 | 否 | 3 | region_id | BTREE |
| metric_tv_sale_v2 | key2 | 否 | 4 | sale_area_id | BTREE |
| metric_tv_sale_v2 | key2 | 否 | 5 | transaction | BTREE |
| metric_tv_sale_v2 | key2 | 否 | 6 | tv_class | BTREE |
| metric_tv_sale_v2 | key2 | 否 | 7 | load_date | BTREE |
| metric_tv_sale_v2 | key3 | 否 | 1 | load_date | BTREE |

## 外键关系

数据库确认：information_schema 未返回跨表外键关系；这不等同于业务上不存在逻辑关联。

## 业务含义标注

### 数据库确认

- 上述表名、字段名、字段类型、可空规则、索引记录和外键记录来自数据库元数据。
- 本次没有读取业务表行，也没有执行 SELECT *、导出、截图或 dump。

### Agent 推测

- metric_、sub_、recharge_、online_、sale_ 等命名只能作为后续探索线索；未结合业务文档或人工确认前，不将其当作已确认业务含义。
- 日期字段的口径、时区、去重规则、指标定义和表间业务关系均未在本文件中推断。

## 提交边界

- 允许提交：本文件中的结构元数据、确认状态、检查时间、授权表数量和 schema fingerprint。
- 禁止提交：任何配置文件内容、连接信息、凭据、原始 SHOW GRANTS、原始 DDL、业务数据、样本值和未脱敏日志。
- 本文件未自动 commit、push，也未发送到飞书。
