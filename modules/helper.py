
def formatSize(size):
  return formatNumber(size, ["bytes", "K", "M", "G", "T"])

def formatSpeed(bps):
  return formatNumber(bps, ["bytes/s", "K/s", "M/s", "G/s", "T/s"])

def formatNumber(number, units):
  i = 0
  while number >= 1024 and i < len(units):
    number /= 1024
    i += 1
  return "%.1d%s" % (number, units[i])