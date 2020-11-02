import os, subprocess, time, sys, yaml, gzip, datetime

def prog_bar(total, done, present="In Progress", past="complete"):
    ratio = int((done / total) * 40)
    black = ratio * "■"
    white = (40 - ratio) * " "
    print(f"{present}... {black}{white}| {done}/{total} {past}", flush=True, end="\r")

def get_value(value):
    if not value[0]: value = input(f"Please enter {value[1]}.>")
    return value

def slash(folder_path):
    if os.path.isdir(folder_path):
        if folder_path[-1] != "/": folder_path += "/"
    else:
        sys.exit(f"{folder_path} is an invalid folder path.")
    return folder_path

def no_blanks(_list):
    while "" in _list:
        _list.remove("")
    return _list

def check_validity(name):
    unusable = [" ", ".", "-", "/", ":", ",", "?", "!", ";", "(", ")", "[", "]", "{", "}", "#", "@", "\\", "=", "&",
                ">", "<"]
    while any(punctuation in name for punctuation in unusable):
        name = input("Capture name cannot include punctuation (except underscore _). Please re-enter: >")
    return name

def generate_cdx(warc_file_or_folder, name="autoindex.cdxj"):
    if os.path.isfile(warc_file_or_folder):
        cdx = warc_file_or_folder.replace(".warc.gz", ".cdxj")
        os.system(f"cdxj-indexer {warc_file_or_folder} > {cdx}")
    elif os.path.isdir(warc_file_or_folder):
        folder = slash(warc_file_or_folder)
        warcs = [x for x in os.listdir(folder)]
        cdx = f"{folder}{name}"
        for warc in warcs:
            os.system(f"cdxj-indexer {folder}{warc} >> {cdx}")
    else:
        sys.exit(f"{warc_file_or_folder} is an invalid file or folder path.")

    return cdx

def to_pywb(warc_file_or_folder, coll_name):
    home = slash(os.path.expanduser("~"))
    os.chdir(home)
    if not os.path.isdir(f"collections/{coll_name}"):
        os.system(f"wb-manager init {coll_name}")
    if os.path.isfile(warc_file_or_folder):
        os.system(f"wb-manager add {coll_name} {warc_file_or_folder}")
    elif os.path.isdir(warc_file_or_folder):
        folder = slash(warc_file_or_folder)
        warcs = [x for x in os.listdir(folder)]
        for warc in warcs:
            os.system(f"wb-manager add {coll_name} {folder}{warc}")

def combine_warcs(folder):
    folder = slash(folder)
    warcgzs = [x for x in os.listdir(folder) if ".warc.gz" in x]

    for warc in warcgzs:
        with gzip.open(f"{folder}{warc}", "rb") as source, open(f"{folder}{warc[:-3]}", "wb") as dest:
            dest.write(source.read())

    warcs = [x for x in os.listdir(folder) if x[-5:] == ".warc"]
    for warc in warcs[1:]:
        os.system(f"cat {folder}{warc} >> {folder}{warcs[0]}")
        os.remove(f"{folder}{warc}")

    with open(f"{folder}{warcs[0]}", "rb") as source, gzip.open(f"{folder}combined.warc.gz", "wb") as dest:
        dest.write(source.read())

    return f"{folder}combined.warc.gz"

class Yaml(object):
    def __init__(self, urls, location, capture_name=(False, "Capture Name"), crawl_name=False):
        self.urls = list(set(no_blanks(urls)))
        self.location = slash(location)
        self.capture_name = check_validity(get_value(capture_name))
        self.crawl_name = self.capture_name if not crawl_name else crawl_name

        self.yaml_loc = f"{self.location}{self.crawl_name}.yaml"

        self.domains = [{"domain": x.split("/")[2]} for x in self.urls]
        self.domains = [dict(t) for t in {tuple(d.items()) for d in self.domains}]

        self.template = """{'crawls': [{'name': self.crawl_name, 'crawl_type': "(crawl_type)", 'crawl_depth': "(crawl_depth)",
                                'num_browsers': 1, 'num_tabs': "(num_tabs)", 'coll': self.capture_name,
                                'mode': "(mode)", 'behavior_max_time': 80,
                                'browser': "(browser)", 'cache': 'always', 'scopes': self.domains,
                                'seed_urls': self.urls}]}"""

    def custom(self):
        with open(f"{self.location}yaml_template.yaml", "w") as dest:
            yaml.dump(eval(self.template), dest, sort_keys=False)

        default = input(f"""
Customise the YAML at {self.location}yaml_template.yaml
(Do not change 'name' or 'coll' fields)
When happy with the template, save it and hit return here in the terminal>""")

        os.rename(f"{self.location}yaml_template.yaml", f"{self.location}{self.crawl_name}.yaml")

        print("YAML created")

    def write(self, crawl_type="custom", crawl_depth=3, num_browsers=1, num_tabs=4, mode="record",
                 browser="chrome:84"):
        if self.crawl_name[:5] == "PATCH": crawl_depth = 0
        self.yaml_template = self.template.replace('"(', '')
        self.yaml_template = self.yaml_template.replace(')"', '')

        self.yaml_template = eval(self.yaml_template)

        with open(f"{self.location}{self.crawl_name}.yaml", "w") as dest:
            yaml.dump(self.yaml_template, dest, sort_keys=False)

        print("YAML created")

    def start(self, progress=True):
        home = slash(os.path.expanduser("~"))
        bx_loc = f"{home}browsertrix/webarchive/collections/{self.capture_name}/"

        def command():
            command = f"browsertrix crawl create {self.yaml_loc}"
            print("Creating New Crawl, Please Wait...")
            result = subprocess.check_output(command, shell=True).decode("utf-8")
            x = result.split("\n")[1:3]
            print(x[0] + "\n" + x[1])
            print("Check here for more details: http://localhost:8000")
            crawl_id = x[0].split(": ")[1]

            return crawl_id

        def check(crawl_id):
            try:
                info = subprocess.check_output(f"browsertrix crawl info {crawl_id}", shell=True).decode("utf-8")
            except:
                return False

            info = yaml.safe_load(info)
            return info

        def running():
            out = check(crawl_id)
            stuck = 0
            while out:
                if out["status"] != "done":
                    #os.system(f'sudo browsertrix crawl logs {crawl_id} > {self.location}logs.txt')
                    if progress:
                        done = int(out["num_seen"]) - int(out["num_queue"])
                        prog_bar(int(out["num_seen"]), done, "Crawling", "URLs crawled")
                    if out["num_queue"] == 0:
                        stuck += 1
                        if stuck == 3:
                            os.system(f"browsertrix crawl remove {crawl_id}")
                            out = False
                            continue
                        elif stuck > 1:
                            print(f"\nIt looks as though the crawler is stuck.\n"
                                  f"To fix, open http://localhost:9020/attach/{out['browsers'][0]} and click through the active tabs.\n"
                                  f"If that doesn't work, remove the crawl.", end="\r")
                    else:
                        stuck = 0
                    time.sleep(30)
                    #os.system(f'sudo browsertrix crawl logs {crawl_id} > {self.location}logs.txt')
                    out = check(crawl_id)

                elif out["status"] == "done":
                    break

            if not out:
                print(f"\nCrawl {self.crawl_name} aborted.\n")
            else:
                os.system(f'sudo browsertrix crawl logs {crawl_id} > {self.location}logs.txt')
                os.system(f"browsertrix crawl remove {crawl_id}")
                print(f"\nCrawl {self.crawl_name} finished.")

            if not os.path.isfile(f"{bx_loc}indexes/autoindex.cdjx"):
                os.system(f"sudo chmod -R 777 {bx_loc}")
                cdx = generate_cdx(f"{bx_loc}archive/")
                os.system(f"mv {cdx} {bx_loc}indexes/autoindex.cdxj")

        if os.path.isfile(f"{self.location}{self.crawl_name}.yaml"):
            crawl_id = command()
        else:
            self.write()
            crawl_id = command()

        out = check(crawl_id)
        if out:
            time.sleep(7)
            running()
        else:
            sys.exit(f"Crawl {self.crawl_name} failed to launch")


class Cdx(object):
    def __init__(self, cdx=(False, "CDX location")):
        self.cdx = get_value(cdx)
        try:
            with open(cdx, "r") as self.cdx:
                self.cdx = self.cdx.read().split("\n")
        except:
            sys.exit(f"It seems there is no CDX at location {cdx}")

        self.cdx = no_blanks(self.cdx)
        self.cdx = [eval(line.split(" ", 2)[2]) for line in self.cdx]

    def create_rud(self):
        self.rud = {}
        for x in range(0, 1000):
            self.rud[x] = None

        for line in self.cdx:
            if "status" not in line.keys():
                continue
            try:
                self.rud[int(line["status"])].append(line["url"])
            except:
                self.rud[int(line["status"])] = [line["url"]]

        return Response_url_dict(self.rud)


class Response_url_dict(object):
    def __init__(self, rud):
        self.rud = rud
        self.present = [code for code in rud if rud[code]]
        for code in self.present:
            l = []
            [l.append(url) for url in self.rud[code] if url not in l]
            self.rud[code] = l

    def deduplicate(self):
        for code in self.present:
            if code == 200:
                continue
            for url in self.rud[code]:
                if url in self.rud[200]:
                    print(url)
                    self.rud[code].remove(url)
        self.present = [code for code in self.rud if self.rud[code]]
        return self

    def get_counts(self):
        return {code: len(self.rud[code]) for code in self.rud if self.rud[code]}

    def count_code(self, http_response):
        if self.rud[http_response]:
            return len(self.rud[http_response])
        else:
            return 0

    def get_urls(self, list_of_codes=(False, "a list of response codes separated by a comma e.g. 403,404,500")):
        self.codes = get_value(list_of_codes)
        urls = []

        while type(self.codes) == str:
            self.codes = self.codes.split(",")
            try:
                self.codes = [int(code.strip()) for code in self.codes if
                          int(code.strip()) in range(0, 1000)]
            except:
                self.codes = input(f"\nThere is an issue with your list of response codes to patch: {self.codes}\n"
                                   f"Please re-enter in following format: 403,404,500)\n>")

        for code in self.codes:
            if self.rud[code] != None:
                urls += (self.rud[code])

        return urls


def capture(url_list, capture_name=(False, "name of Capture"), area=(False, "path to directory in which to locate this crawl"),
            crawl_depth=3, num_tabs=5, mode="record", browser="chrome:84", patch=None,
            patch_codes=(False, "a list of response codes separated by a comma e.g. 403,404,500"), progress=True):
    def crawl(urls, crawl_name, patch=patch):
        yaml_object = Yaml(urls, capture_loc, capture_name, crawl_name)
        yaml_object.write(crawl_depth=crawl_depth, num_tabs=num_tabs, mode=mode, browser=browser)
        yaml_object.start(progress)
        cdx = Cdx(f"{home}browsertrix/webarchive/collections/{capture_name}/indexes/autoindex.cdxj")
        rud = cdx.create_rud()
        rud.deduplicate()
        counts = rud.get_counts()

        print("Here are the HTTP responses for this crawl and their frequency:\ncode : freq")
        if patch_count > 0:
            for code in counts:
                counts[code] = counts[code] - crawls[patch_count-1]["rescode_counts"][code]

        for x in counts:
            print(x, ":", counts[x])  # minus previous

        while patch not in ["y", "n"]:
            patch = input("Would you like to patch? [Y/n]").lower()

        if patch == "y":
            rerun = rud.get_urls(patch_codes)
        else:
            rerun = False

        crawl_details = {"name": crawl_name, "rescode_counts": counts, "rerun": rerun}

        return crawl_details

    auto=True if patch else False
    timestamp = datetime.datetime.now().strftime("%d%m%Y")
    urls = no_blanks(url_list)
    capture_name = check_validity(get_value(capture_name)) + "_" + timestamp

    area = slash(get_value(area))
    capture_loc = area + capture_name

    if not os.path.isdir(capture_loc):
        os.mkdir(capture_loc)

    capture_loc = slash(capture_loc)
    home = slash(os.path.expanduser("~"))
    crawls = {}

    patch_count = 0
    crawl_details = crawl(urls, capture_name)
    crawls[patch_count] = crawl_details
    rerun = crawls[patch_count]["rerun"]
    while rerun:
        run_patch="n" if auto else None
        patch_count += 1
        crawl_details = crawl(rerun, ("PATCH"*patch_count + capture_name), patch=run_patch)
        crawls[patch_count] = crawl_details
        rerun = crawls[patch_count]["rerun"]

    os.system(f"sudo cp -r {home}browsertrix/webarchive/collections/{capture_name} {capture_loc}")
    os.system(f"sudo chmod -R 777 {capture_loc}")
    print(f"Capture complete. Crawl files located in:\n{capture_loc}{capture_name}/")
