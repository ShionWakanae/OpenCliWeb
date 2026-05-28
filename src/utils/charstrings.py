def display_width(s):
    return sum(2 if "\u4e00" <= ch <= "\u9fff" else 1 for ch in s)


def truncate_by_width_approx(s, max_width):
    width = 0
    for i, ch in enumerate(s):
        ch_width = 2 if "\u4e00" <= ch <= "\u9fff" else 1
        if width + ch_width > max_width:
            return s[:i]
        width += ch_width
    return s
