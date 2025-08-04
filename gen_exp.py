


# print array

str = ""
for i in range(100):
    if i < 5:
        dis = 100
    elif i < 20:
        dis = 500
    elif i < 50:
        dis = 1000
    elif i < 80:
        dis = 2000
    elif i < 90:
        dis = 5000
    else:
        dis = 10000
    exp = i * dis
    str += f"{exp}, "

print(f"[{str[:-2]}]")  # remove last comma and space