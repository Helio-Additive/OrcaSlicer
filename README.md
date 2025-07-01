<h1> <p "font-size:200px;"><img align="left" src="https://github.com/SoftFever/OrcaSlicer/blob/main/resources/images/OrcaSlicer.ico" width="100"> Orca Slicer</p> </h1>

[![Build all](https://github.com/SoftFever/OrcaSlicer/actions/workflows/build_all.yml/badge.svg?branch=main)](https://github.com/Helio-Additive/OrcaSlicer/actions)
<br>Orca Slicer is an open source slicer for FDM printers. 

⚠️ Note that this is a a customized fork of Orca Slicer with **cloud-based thermal simulation** built right in.

This version adds Helio’s physics-driven thermal simulation directly into your slicing workflow. Instantly visualize layer-by-layer thermal behavior and optimize for print reliability;  no extra software needed.

## Follow Offical Orca Slicer Channels
Stay connected with us:

[![Twitter](https://img.shields.io/badge/Twitter-1DA1F2?logo=twitter&logoColor=white&style=flat)](https://twitter.com/real_OrcaSlicer)

Join our Discord community here:<br>
<a href="https://discord.gg/P4VE9UY9gJ"><img src="https://img.shields.io/static/v1?message=Discord&logo=discord&label=&color=7289DA&logoColor=white&labelColor=&style=for-the-badge" height="35" alt="discord logo"/> </a>
 
 <h3>🚨🚨🚨Important Security Alert🚨🚨🚨</h3> 

The only official platforms for OrcaSlicer are **our GitHub project page**, <a href="https://orcaslicer.com/">**orcaslicer.com**</a>, and the <a href="https://discord.gg/P4VE9UY9gJ">**official Discord channel**</a>.

Please be aware that "**orcaslicer.net**", "**orcaslicer.co**" or "**orca-slicer.com**" are NOT an official website for OrcaSlicer and may be potentially malicious. These sites appear to use AI-generated content, lacking genuine context and seems to exist solely to profit from advertisements. Worse, it may redirect download links to harmful sources. For your safety, avoid downloading OrcaSlicer from this site as the links may be compromised. 

If you see the above sites in your searches, report them as spam or unsafe to the search engine. This small action will assist everyone.

We deeply value our OrcaSlicer community and appreciate all the social groups that support us. However, it is crucial to address the risk posed by any group that falsely claims to be official or misleads its members. If you encounter such a group or are part of one, please assist by encouraging the group owner to add a clear disclaimer or by alerting its members.

Thank you for your vigilance and support in keeping our community safe!

## 🚀 Added Helio Additive Features

### 🔥 Thermal Simulation Integration
- Slice as usual or toggle on **"Slice with Helio"** to generate a full thermal simulation of your print.
- View **layer time dependent temperature** directly in the **Preview panel**, alongside standard slicer settings.
- Get insight into thermal consistency, cooling behavior, and critical hotspots in your model.

### 🌐 Cloud-Based Processing
- Simulation is offloaded to the cloud for fast processing – no local compute needed.
- Requires internet connection and a personal api key for usage.
- Simulations are offered for free

### 🧪 Experimental Features
- Integrated thermal overlays in the Preview tab.
- Thermal results viewable layer by layer, road by road or across the full print.

## Wiki
The wiki below aims to provide a detailed introduction to and support for **Orca Slicer, Helio Edition**.

Please note that the wiki is a work in progress. We appreciate your patience as we continue to develop and improve it!

📝 **[Access the wiki here](https://wiki.helioadditive.com/en/orcaslicer)**  

## Download Helio Additive's Orca Slicer Version

Download our customized version of OrcaSlicer with **cloud-based thermal simulation** built in.

### Stable Release
📥 **[Download the Latest Stable Release](https://github.com/Helio-Additive/OrcaSlicer/releases)**  
Visit our GitHub Releases page for the latest stable version of Orca Slicer, recommended for most users.

## How to set up

📝 **[View Our Guide On Setting Up Supported Printer And Material Profiles](https://docs.helioadditive.com/en/slicers/orcaslicer/#initial-set-up)** 

## How to use
1. Slice your model as usual.
2. Enable **“Slice with Helio”** before slicing.
3. Once slicing and simulation completes, view the thermal results in the Preview panel.
4. You can toggle between regular preview parameters and thermal simulation overlays.

For more information on reading and improving results, refer to our [documentation here](https://docs.helioadditive.com/en/slicers/orcaslicer/#how-to-interpret-thermal-index). 

## Note (from the Original Orca Slicer Project): 
If you're running Klipper, it's recommended to add the following configuration to your `printer.cfg` file.
```
# Enable object exclusion
[exclude_object]

# Enable arcs support
[gcode_arcs]
resolution: 0.1
```

# Supports
**Orca Slicer** is an open-source project and I'm deeply grateful to all my sponsors and backers.   
Their generous support enables me to purchase filaments and other essential 3D printing materials for the project.   
Thank you! :)

### Sponsors:  
<table>
<tr>
<td>
<a href="https://qidi3d.com/">
    <img src="SoftFever_doc\sponsor_logos\QIDI.png" alt="QIDI" width="96" height="">
</a>
</td>
<td>
<a href="https://bigtree-tech.com/">
    <img src="SoftFever_doc\sponsor_logos\BigTreeTech.png" alt="BIGTREE TECH" width="96" height="">
</a>
</td>
</tr>
</table>

### Backers:  
**Ko-fi supporters**: [Backers list](https://github.com/user-attachments/files/16147016/Supporters_638561417699952499.csv)

## Support me  
<a href="https://github.com/sponsors/SoftFever"><img src="https://img.shields.io/static/v1?label=Sponsor&message=%E2%9D%A4&logo=GitHub&color=%23fe8e86" width="130"></a>

<a href="https://ko-fi.com/G2G5IP3CP"><img src="https://ko-fi.com/img/githubbutton_sm.svg" width="200"></a>

[![PayPal](https://img.shields.io/badge/PayPal-00457C?style=for-the-badge&logo=paypal&logoColor=white)](https://paypal.me/softfever3d)


## Some background
OrcaSlicer was originally forked from Bambu Studio, it was previously known as BambuStudio-SoftFever.

[Bambu Studio](https://github.com/bambulab/BambuStudio) is forked from [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) by Prusa Research, which is from [Slic3r](https://github.com/Slic3r/Slic3r) by Alessandro Ranellucci and the RepRap community.
Orca Slicer incorporates a lot of features from [SuperSlicer](https://github.com/supermerill/SuperSlicer) by @supermerill
Orca Slicer's logo is designed by community member Justin Levine(@freejstnalxndr)  


# License
Orca Slicer is licensed under the GNU Affero General Public License, version 3. Orca Slicer is based on Bambu Studio by BambuLab.

Bambu Studio is licensed under the GNU Affero General Public License, version 3. Bambu Studio is based on PrusaSlicer by PrusaResearch.

PrusaSlicer is licensed under the GNU Affero General Public License, version 3. PrusaSlicer is owned by Prusa Research. PrusaSlicer is originally based on Slic3r by Alessandro Ranellucci.

Slic3r is licensed under the GNU Affero General Public License, version 3. Slic3r was created by Alessandro Ranellucci with the help of many other contributors.

The GNU Affero General Public License, version 3 ensures that if you use any part of this software in any way (even behind a web server), your software must be released under the same license.

Orca Slicer includes a pressure advance calibration pattern test adapted from Andrew Ellis' generator, which is licensed under GNU General Public License, version 3. Ellis' generator is itself adapted from a generator developed by Sineos for Marlin, which is licensed under GNU General Public License, version 3.

The Bambu networking plugin is based on non-free libraries from BambuLab. It is optional to the Orca Slicer and provides extended functionalities for Bambulab printer users.

