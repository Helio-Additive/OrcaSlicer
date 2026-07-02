<div align="center">

<picture>
  <img alt="OrcaSlicer logo" src="resources/images/OrcaSlicer.png" width="15%" height="15%">
</picture>

<h1>Helio Orca Slicer</h1>

<a href="https://github.com/Helio-Additive/OrcaSlicer/actions"><img src="https://github.com/Helio-Additive/OrcaSlicer/actions/workflows/build_all.yml/badge.svg" alt="Build all"></a>

<p>A customized fork of <a href="https://github.com/OrcaSlicer/OrcaSlicer">OrcaSlicer</a> with <b>cloud-based thermal simulation</b> built right in.</p>

<p>This version adds Helio's physics-driven thermal simulation directly into your slicing workflow. Instantly visualize layer-by-layer thermal behavior and optimize for print reliability — no extra software needed.</p>

</div>

# Helio Additive Features

## Thermal Simulation Integration
- Slice as usual or toggle on **"Slice with Helio"** to generate a full thermal simulation of your print.
- View **layer time-dependent temperature** directly in the **Preview panel**, alongside standard slicer settings.
- Get insight into thermal consistency, cooling behavior, and critical hotspots in your model.

## Cloud-Based Processing
- Simulation is offloaded to the cloud for fast processing — no local compute needed.
- Requires internet connection and a personal API key for usage.
- Simulations are offered for free.

## Experimental Features
- Integrated thermal overlays in the Preview tab.
- Thermal results viewable layer by layer, road by road, or across the full print.

# How to Use Helio Simulation
1. Slice your model as usual.
2. Enable **"Slice with Helio"** before slicing.
3. Once slicing and simulation complete, view the thermal results in the Preview panel.
4. Toggle between regular preview parameters and thermal simulation overlays.

For more information on reading and improving results, refer to the [Helio documentation](https://docs.helioadditive.com/en/slicers/orcaslicer/#how-to-interpret-thermal-index).

# Setup

**[View our guide on setting up supported printer and material profiles](https://docs.helioadditive.com/en/slicers/orcaslicer/#initial-set-up)**

# Wiki

The [Helio OrcaSlicer wiki](https://wiki.helioadditive.com/en/orcaslicer) provides detailed documentation for this fork, including Helio-specific features and setup.

For general OrcaSlicer settings, see the [upstream OrcaSlicer wiki](https://www.orcaslicer.com/wiki).

# Download

## Stable Release

📥 **[Download the Latest Stable Release](https://github.com/Helio-Additive/OrcaSlicer/releases/latest)**
Visit the Helio OrcaSlicer releases page for the latest version with thermal simulation built in.

# How to Install

## Windows

Download the **Windows Installer exe** for your preferred version from the [releases page](https://github.com/Helio-Additive/OrcaSlicer/releases).

 - *For convenience there is also a portable build available.*
    <details>
    <summary>Troubleshooting</summary>

    - *If you have troubles to run the build, you might need to install following runtimes:*
    - [MicrosoftEdgeWebView2RuntimeInstallerX64](https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v1.0.10-sf2/MicrosoftEdgeWebView2RuntimeInstallerX64.exe)
        - [Details of this runtime](https://aka.ms/webview2)
        - [Alternative Download Link Hosted by Microsoft](https://go.microsoft.com/fwlink/p/?LinkId=2124703)
    - [vcredist2019_x64](https://github.com/OrcaSlicer/OrcaSlicer/releases/download/v1.0.10-sf2/vcredist2019_x64.exe)
        -  [Alternative Download Link Hosted by Microsoft](https://aka.ms/vs/17/release/vc_redist.x64.exe)
        -  This file may already be available on your computer if you've installed visual studio.  Check the following location: `%VCINSTALLDIR%Redist\MSVC\v142`
    </details>

## Mac

1. Download the DMG for your computer: `arm64` version for Apple Silicon and `x86_64` for Intel CPU.
2. Drag OrcaSlicer.app to Application folder.
3. *If you want to run a build from a PR, you also need to follow the instructions below:*

    <details>
    <summary>Quarantine</summary>

    - Option 1 (You only need to do this once. After that the app can be opened normally.):
      - Step 1: Hold _cmd_ and right click the app, from the context menu choose **Open**.
      - Step 2: A warning window will pop up, click _Open_

    - Option 2:
      Execute this command in terminal:

      ```shell
      xattr -dr com.apple.quarantine /Applications/OrcaSlicer.app
      ```

    - Option 3:
        - Step 1: open the app, a warning window will pop up  
            ![mac_cant_open](./SoftFever_doc/mac_cant_open.png)
        - Step 2: in `System Settings` -> `Privacy & Security`, click `Open Anyway`:  
            ![mac_security_setting](./SoftFever_doc/mac_security_setting.png)
    </details>

## Linux (Ubuntu)

### Flathub (Recommended)

OrcaSlicer is available through FlatHub:

<a href='https://flathub.org/apps/com.orcaslicer.OrcaSlicer'><img width='240' alt='Download on Flathub' src='https://dl.flathub.org/assets/badges/flathub-badge-en.png'/></a>

Install from the command line:

```shell
flatpak install flathub com.orcaslicer.OrcaSlicer
flatpak run com.orcaslicer.OrcaSlicer
```

It can also be installed through graphical software managers (KDE Discover, GNOME Software, etc.) when Flathub is enabled. Search for **OrcaSlicer** in your software center.

### AppImage

AppImages are published for both **x86_64** and **aarch64** (ARM64). Pick the file matching your CPU — the ARM64 build has `aarch64` in its name (e.g. `OrcaSlicer_Linux_AppImage_Ubuntu2404_aarch64_*.AppImage`).

 1. Download App image from the [releases page](https://github.com/OrcaSlicer/OrcaSlicer/releases).
 2. Double click the downloaded file to run it.

 3. If you run into trouble executing it, try this command in the terminal:
    `chmod +x /path_to_appimage/OrcaSlicer_Linux.AppImage`

# How to Compile

For build instructions, see the [upstream OrcaSlicer Wiki - How to build](https://www.orcaslicer.com/wiki/How-to-build) page. The build process for this fork is the same.

# Official OrcaSlicer Community

This fork is built on top of [OrcaSlicer](https://github.com/OrcaSlicer/OrcaSlicer). Stay connected with the upstream project:

- **Website**: [orcaslicer.com](https://www.orcaslicer.com/)
- **Twitter/X**: [@real_OrcaSlicer](https://twitter.com/real_OrcaSlicer)
- **Discord**: [OrcaSlicer Discord](https://discord.gg/P4VE9UY9gJ)

# Klipper Note

If you're running Klipper, it's recommended to add the following configuration to your `printer.cfg` file.

```gcode
# Enable object exclusion
[exclude_object]

# Enable arcs support
[gcode_arcs]
resolution: 0.1
```

# Supports

**OrcaSlicer** is an open-source project and I'm deeply grateful to all my sponsors and backers.  
Their generous support enables me to purchase filaments and other essential 3D printing materials for the project.  
Thank you! :)

## Sponsors:

<table>
<tr>
<td>
<a href="https://qidi3d.com/" style="display:inline-block; border-radius:8px; background:#fff;">
  <img src="SoftFever_doc\sponsor_logos\QIDI.png" alt="QIDI" width="100" height="100">
</a>
</td>
<td>
<a href="https://bigtree-tech.com/" style="display:inline-block; border-radius:8px; background:#222;">
    <img src="SoftFever_doc\sponsor_logos\BigTreeTech.png" alt="BIGTREE TECH" width="100" height="100">
</a>
</td>
</tr>
</table>

## Backers:

**Ko-fi supporters** ☕: [Backers list](https://github.com/user-attachments/files/16147016/Supporters_638561417699952499.csv)

## Support me

<a href="https://github.com/sponsors/SoftFever"><img src="https://img.shields.io/badge/GitHub%20Sponsors-30363D?style=flat&logo=GitHub-Sponsors&logoColor=EA4AAA" height="50"></a>
<a href="https://ko-fi.com/G2G5IP3CP"><img src="https://img.shields.io/badge/Support_me_on_Ko--fi-FF5E5B?style=flat&logo=ko-fi&logoColor=white" height="50"></a>
<a href="https://paypal.me/softfever3d"><img src="https://img.shields.io/badge/PayPal-003087?style=flat&logo=paypal&logoColor=fff" height="50"></a>

## Some Background

Open-source slicing has always been built on a tradition of collaboration and attribution. [Slic3r](https://github.com/Slic3r/Slic3r), created by Alessandro Ranellucci and the RepRap community, laid the foundation. [PrusaSlicer](https://github.com/prusa3d/PrusaSlicer) by Prusa Research built on Slic3r and acknowledged that heritage. [Bambu Studio](https://github.com/bambulab/BambuStudio) in turn forked from PrusaSlicer, and [SuperSlicer](https://github.com/supermerill/SuperSlicer) by @supermerill extended PrusaSlicer with community-driven enhancements. Each project carried the work of its predecessors forward, crediting those who came before.

OrcaSlicer began in that same spirit, drawing from BambuStudio, PrusaSlicer, and ideas inspired by CuraSlicer and SuperSlicer. But it has since grown far beyond its origins. Through relentless innovation — introducing advanced calibration tools, precise wall and seam control, tree supports, adaptive slicing, and hundreds of other features — OrcaSlicer has become the most widely used and actively developed open-source slicer in the 3D printing community. Many of its innovations have been adopted by other slicers, making it a driving force for the entire industry.

The OrcaSlicer logo was designed by community member Justin Levine (@freejstnalxndr).

# License
- **OrcaSlicer** is licensed under the GNU Affero General Public License, version 3.
- The **GNU Affero General Public License**, version 3 ensures that if you use any part of this software in any way (even behind a web server), your software must be released under the same license.
- OrcaSlicer includes a **pressure advance calibration pattern test** adapted from Andrew Ellis' generator, which is licensed under GNU General Public License, version 3. Ellis' generator is itself adapted from a generator developed by Sineos for Marlin, which is licensed under GNU General Public License, version 3.
- The **Bambu networking plugin** is based on non-free libraries from BambuLab. It is optional to the OrcaSlicer and provides extended functionalities for Bambulab printer users.
