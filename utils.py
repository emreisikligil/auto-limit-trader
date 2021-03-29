def find_min_delta(amount):
    dot_ind = amount.find(".")
    if dot_ind < 0:
        return 1.0
    float_len = len(amount) - dot_ind - 1
    if float_len <= 0:
        return 1.0
    return float("0." + "0" * (float_len - 1) + "1")
