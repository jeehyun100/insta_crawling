import pandas as pd


class url_change(object):
    def __init__(self):
        return print("init class")
    def make_df(self):
        data1 = [['A',1],['B',2],['C',3]]
        data2 = [['E', 1], ['F', 2], ['C', 2]]

        df1 = pd.DataFrame(data1, columns=['id', 'ModifyDatetime'])
        df2 = pd.DataFrame(data2, columns=['id', 'ModifyDatetime'])
        return df1, df2
    def save_df(self):
        return None
    def merge(self, df1, df2):
        result = pd.merge(df1, df2, how='outer', on=['id'])
        #df['period'] = df[['Year', 'quarter']].apply(lambda x: ''.join(x), axis=1)
        # def my_test2(row):
        #     ....:
        #     return row['a'] % row['c']
        #df['Value'] = df.apply(my_test2, axis=1)
        result = result.fillna(0)
        result['new'] = result.apply(self.compare_modify_time,axis=1)
        return result
    def compare_modify_time(self, row):
        original_time = row['ModifyDatetime_x']
        modify_time = row['ModifyDatetime_y']
        if original_time  < modify_time:
            result = modify_time
        else:
            result = original_time
        return result



def main():
    util_cls = url_change()
    pd1, pd2 = util_cls.make_df()
    merge_df = util_cls.merge(pd1, pd2)

    print(merge_df)

if __name__ == "__main__":

    main()
