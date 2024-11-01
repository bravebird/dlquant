
def test_get_targets():
    from utils.data import get_targets_list_from_csv
    target_list = get_targets_list_from_csv()
    print("*" * 10)
    print(target_list)
    print(len(target_list))


def test_get_stock_data():
    from load_data.download_xt_data import get_data_from_local
    df = get_data_from_local()
    print('\n')
    print(df.head())
    print(df.columns)
    print(df.shape)


def test_get_darts_timeseries():
    from load_data.multivariate_timeseries import prepare_timeseries_data
    data_dict = prepare_timeseries_data('training')
    print(data_dict.keys())
    predicting_data_dict = prepare_timeseries_data('predicting')
    print(predicting_data_dict.keys())
    print(predicting_data_dict['train'].data_array().sizes)
    print(predicting_data_dict['test'].time_index)


def test_get_data_from_local():
    from load_data.download_xt_data import get_data_from_local
    data = get_data_from_local()
    data.to_csv("data/stock_data.csv")