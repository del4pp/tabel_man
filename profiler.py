import pstats

# Завантажте файл профілювання
stats = pstats.Stats('profile_results.prof')

# Виведіть найбільш часовитратніші функції
stats.strip_dirs().sort_stats('time').print_stats(10)
