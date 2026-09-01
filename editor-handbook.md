# Editor Handbook

## Introduction
This is the handbook for the editors, please go through the whole handbook (not long) before you edit.


## File Structure
Following is the tree of files in this repo, please check the notes for each file to have the understanding of how the purposes of each file.
```text
.
├── _config_prod.yml (config file for the production deployment, do not edit)
├── _config.yml (config file for the github page deployment, do not edit)
├── _includes (website structure, contact maintainer for editing)
│   ├── footer.html
│   └── header.html
├── _layouts (website structure, contact maintainer for editing)
│   └── default.html
├── .gitignore (git ignore, contact maintainer for editing)
├── archive (archive webpages, please have new folders within for different workshops)
│   ├── 2024-jan (a workshop archive directory)
│   │   ├── index.html (webpage)
│   │   └── xxx.png (and single-use resources)
│   ├── 2024-oct
│   │   └── index.html
│   └── 2025-jul
│       └── index.html
├── assets (reusable resources directory)
│   ├── css (website structure, contact maintainer for editing)
│   │   ├── extra.scss
│   │   └── main.css
│   └── pic (reusable pictures)
│       ├── banner-large.jpg
│       ├── banner.jpg
│       └── favicon.png
├── editor-handbook.md (this file)
├── index.html (homepage directory)
├── LICENSE (do not edit)
├── program (program directory)
│   └── index.html (webpage)
├── README.md (repo README)
├── registration (registration directory)
│   └── index.html (webpage)
└── venue (venue directory)
    └── index.html (webpage)
```


## Principles of Editing
Please place resuable resources in ```./assets```, and single-use resources in the related directory.


## How to Edit
As the webpages for the website are explicitly seperated into different directories, 
editors just need to edit the corresponding file within the dedicated directory.
For example, if the editor would like to edit program webpage, then the file needs to be amended 
is ```./program/index.html```.

Meanwhile, please check with maintainer if anything related to structure needs to be amended.

The website is still in construction, thus the layout might be imperfect, we are continously working on this to provide a better version.

## Local Testing

Please check [here](https://docs.github.com/en/pages/setting-up-a-github-pages-site-with-jekyll/testing-your-github-pages-site-locally-with-jekyll) for detailed instructions.

TL;DR:
1. First install [Jekyll](https://jekyllrb.com/docs/installation/)
2. Open terminal and switch working directory to this repo.
3. use ```jekyll serve --baseurl=""``` to start the local deployment, 
then visit [127.0.0.1:4000](http://127.0.0.1:4000) to check the <span style="color:red">real-time</span> deployment.

As the local one is updating in real-time, you can edit,save and refresh the webpage to check the result.

## Website Deployment
Currently we are deploying a 2-stage website deployment:
1. [itseg-mq.github.io/tacps](https://itseg-mq.github.io/tacps)  for staging, hosted by GitHub Pages
2. [tacps.org](https://tacps.org) for production, self-hosted

The GitHub Pages can provide a quick look on the result.

The self-hosted one has Cloudflare caching for faster access around the world, it will check on github page update every 1 min and deploy update automatically if any. 
