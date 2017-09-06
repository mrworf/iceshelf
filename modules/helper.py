
def formatTime(seconds):
  if seconds < 60:
    # ss
    return "%ds" % seconds
  elif seconds < 3600:
    # mm:ss
    return "%dm %02ds" % (seconds / 60, seconds % 60)
  elif seconds < 86400:
    # hh:mm:ss
    return "%dh %02dm %02ds" % (seconds / 3600, (seconds % 3600) / 60, seconds % 60)
  else:
    # dd:hh:mm:ss
    return "%dd %02dh %02dm %02ds" % (seconds / 86400, (seconds % 86400) / 3600, (seconds % 3600) / 60, seconds % 60)

def formatSize(size):
  return formatNumber(size, [" bytes", "K", "M", "G", "T"])

def formatSpeed(bps):
  return formatNumber(bps, [" bytes/s", "K/s", "M/s", "G/s", "T/s"])

def formatNumber(number, units):
  i = 0
  while number >= 1024 and i < len(units):
    number /= 1024
    i += 1
  return "%.1d%s" % (number, units[i])
