import sys
import os
from scrapy.cmdline import execute

sys.path.append(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from capture_instagram.utils import ConsoleUtil


# tag = 'sponsor'
# Get tag to be crawled
while True:
    tag = ConsoleUtil.get_string('Please input a tag (ad,sponsored,pr,gifted,advertising...)')
    tag = tag.strip()
    if tag:
        break
print('\n\n')

# Get data step to retrieve
contents = [
    'Crawl post links list',
    'Crawl post details',
    'Crawl user followers num'
]
while True:
    print('Select the content you want to crawl')
    for i in range(len(contents)):
        print(f'{i+1} {contents[i]}')
    step = ConsoleUtil.get_valid_input_int('Input selected number:', 0)
    if step in set(range(1, len(contents)+1)):
        break
print('\n\n')

yes_no = ConsoleUtil.get_yes_no(f'Confirm your input：tag={tag}, content={contents[step-1]}，')
print('\n\n')

if not yes_no:
    sys.exit(0)

if step == 1:
    max_count = ConsoleUtil.get_valid_input_int('Input max number of links to craw', 1000)
    # Note: As this crawler for post links can't be yielded, the argument is -a output_file, not -o !!!
    output_file = '..' + os.path.sep + 'data' + os.path.sep + f'post_links_{tag}.txt'
    execute(f'scrapy crawl capture_simple -a tag={tag} -a output_file={output_file} -a max_count={max_count}'.split(' '))
elif step == 2:
    output_file = '..' + os.path.sep + 'data' + os.path.sep + f'posts_{tag}.csv'
    execute(f'scrapy crawl capture_simple -a tag_detail={tag} -o {output_file}'.split(' '))
elif step == 3:
    output_file = '..' + os.path.sep + 'data' + os.path.sep + 'user_follower.csv'
    execute(f'scrapy crawl capture_simple -a user_follower={tag} -o {output_file}'.split(' '))
