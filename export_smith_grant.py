"""
Export the W. Eugene Smith Grant 2026 image set (Prior Use, 40 images) to a folder on the Desktop.

Run from the pli folder on your Mac:
    cd "/Users/jordan/Library/CloudStorage/OneDrive-UniversityofCincinnati/pli"
    python3 ~/Downloads/export_smith_grant.py

Reads the TIFF masters in img/full/<slug>/<frame>.tif and writes, for each image:
JPG, sRGB, 72 dpi, 4000 px on the long edge, named NN_slug_frame.jpg in upload order.
Also writes captions.txt with the numbered captions. Never upscales: if a master is
smaller than 4000 px, or only the 2048 px img/jpg copy exists, it says so.
"""

import io
import os
import sys
from PIL import Image, ImageCms

Image.MAX_IMAGE_PIXELS = None

LONG_EDGE = 4000
DPI = (72, 72)
QUALITY = 95
OUT = os.path.expanduser("~/Desktop/Smith-Grant-2026-Prior-Use")

SELECTION = [
    (1, 'big-oaks-national-wildlife-refuge', '_DSF4301',
     'Big Oaks National Wildlife Refuge, Indiana. In December 1940 the Army took some 56,000 acres of farmland here for the Jefferson Proving Ground and gave the families who lived on it 30 to 120 days to leave; the land never went back to them.'),
    (2, 'big-oaks-national-wildlife-refuge', '_DSF4287',
     'Big Oaks National Wildlife Refuge, Indiana. Taken twice: the Miami, Eel River and Wea ceded this ground to William Henry Harrison in the Treaty of Grouseland in 1805, and the Army condemned the farms that replaced them in 1940.'),
    (3, 'big-oaks-national-wildlife-refuge', '_DSF4307',
     "Big Oaks National Wildlife Refuge, Indiana. From 1941 to 1995 the Army test-fired more than 24 million rounds here; the public may now enter only about 4,000 of the refuge's 50,000 acres, and only after signing a waiver acknowledging the danger."),
    (4, 'fernald-preserve', '_DSF1163',
     'Fernald Preserve, Ohio. Former uranium metal plant; the Department of Energy knew by 1980 that wells near the site were contaminated and did not tell residents for four years, and in 1989 a $78 million settlement covered 9,764 neighbors within five miles.'),
    (5, 'fernald-preserve', '_DSF1155',
     'Fernald Preserve, Ohio. Former uranium metal plant; the long rise on the horizon is the on-site disposal cell holding more than 925,000 cubic yards of low-level radioactive waste, entombed in a $4.4 billion cleanup that ended in 2006.'),
    (6, 'fernald-preserve', '_DSF1138',
     'Fernald Preserve, Ohio. Former uranium metal plant; in 1951 the Atomic Energy Commission bought this farmland from eleven owners and took the land of the three who refused to sell by federal court condemnation.'),
    (7, 'miamisburg-mound', '_DSF4578',
     'Miamisburg Mound, Ohio. The buildings at left are the former Mound Laboratory, across the road, which made polonium and tritium components for nuclear weapons from 1948 to 2003; three classes of its workers have since been added to the federal Special Exposure Cohort for radiation illness. (Public Lands Institute, past work)'),
    (8, 'miamisburg-mound', '_DSF4599',
     'Miamisburg Mound, Ohio. In 1969 a waste line ruptured at Mound Laboratory, across the road, releasing plutonium-238 that a storm during the cleanup washed into the canal, where sampling found it in 1974. (Public Lands Institute, past work)'),
    (9, 'huffman-prairie-flying-field', '_DSF4626',
     'Huffman Prairie Flying Field, Ohio. The sign marks an explosive clear zone on Wright-Patterson Air Force Base, which encloses the field: a Superfund site with some 65 contaminated sites over an aquifer that supplies drinking water to about 500,000 people. (Public Lands Institute, past work)'),
    (10, 'ford-marsh-unit', '_DSF1917',
     'Ford Marsh Unit, Detroit River International Wildlife Refuge, Michigan. The stacks are the Monroe Power Plant, just south, which releases more arsenic into Lake Erie than any other coal plant in the country; Ford gave this marsh to the refuge in 2010 beside its River Raisin Warehouse, an ALCOA munitions plant from 1943 to 1947. (Public Lands Institute, past work)'),
    (11, 'hopewell-culture-national-historical-park', '_DSF1455',
     'Hopewell Culture National Historical Park (Mound City), Ohio. In 1917 the Army leveled nearly every mound here to build Camp Sherman; the mounds seen now were rebuilt from the 1846 survey. (Public Lands Institute, past work)'),
    (12, 'wichita-mountains-national-wildlife-refuge', '_DSF0602',
     'Wichita Mountains National Wildlife Refuge, Oklahoma. McKinley proclaimed the forest reserve here on July 4, 1901, the same day he opened the surrounding Kiowa, Comanche and Apache lands to a settlement lottery under an agreement the Kiowa had opposed for years; an artillery range has run along its south boundary since 1957. (Public Lands Institute, past work)'),
    (13, 'wichita-mountains-national-wildlife-refuge', '_DSF0638',
     'Wichita Mountains National Wildlife Refuge, Oklahoma. After the Red River War of 1874 and 1875, all surviving Comanche bands were confined to the reservation around Fort Sill, and 74 men named as war leaders were imprisoned at Fort Marion, Florida. (Public Lands Institute, past work)'),
    (14, 'palo-duro-canyon', '_DSF0707',
     "Palo Duro Canyon State Park, Texas. On September 28, 1874, Colonel Ranald Mackenzie's troops destroyed the Kiowa, Comanche and Cheyenne winter camps in this canyon and shot more than 1,000 of the roughly 1,400 horses they captured. (Public Lands Institute, past work)"),
    (15, 'palo-duro-canyon', '_DSF0702',
     "Palo Duro Canyon State Park, Texas. The Black Civilian Conservation Corps companies who built the park from 1935 were sent here because the canyon's isolation made segregation easier to enforce, and Black Texans were barred from entering it until 1964. (Public Lands Institute, past work)"),
    (16, 'lathrop-state-park', '_DSF3669',
     "Lathrop State Park, Colorado. After the Colorado National Guard burned the Ludlow tent colony of striking coal miners' families and killed 21 people on April 20, 1914, the fighting reached Walsenburg, two miles east of the park, on April 28 and 29. (Public Lands Institute, past work)"),
    (17, 'yellowstone-national-park', '_DSF2955',
     'Yellowstone National Park, Wyoming. From 1886 to 1918 the Army ran the park from Fort Yellowstone, here at Mammoth Hot Springs, on land withdrawn in 1872 with no cession by or payment to the tribes who lived and hunted here. (Public Lands Institute, past work)'),
    (18, 'prophetstown-state-park', '_DSF2390',
     "Prophetstown State Park, Indiana. Tenskwatawa and Tecumseh's town, home to an estimated 3,000 people from more than a dozen nations, stood on ground ceded in the 1809 Treaty of Fort Wayne; Harrison's forces burned it on November 8, 1811, the day after the Battle of Tippecanoe. (Public Lands Institute, past work)"),
    (19, 'eagle-marsh-nature-preserve', '_DSF3989',
     'Eagle Marsh Nature Preserve, Indiana. On October 6, 1846, the United States forced the last Miami community at the head of the Maumee, several hundred people, onto canal boats for removal to Kansas, splitting the nation into the Miami Tribe of Oklahoma and the Miami Nation of Indiana. (Public Lands Institute, past work)'),
    (20, 'maquoketa-caves-state-park', '_DSF2531',
     "Maquoketa Caves State Park, Iowa. The caves lie inside the Black Hawk Purchase, about six million acres taken from the Sauk and Meskwaki in 1832 as a punitive condition of Black Hawk's defeat and signed while he was held prisoner. (Public Lands Institute, past work)"),
    (21, 'mount-rushmore-national-memorial', '_DSF2820',
     'Mount Rushmore National Memorial, South Dakota. Carved beginning in 1927, without tribal consent, into Tunkasila Sakpe Paha, the Six Grandfathers, a Lakota vision quest site in Black Hills that Congress seized in 1877 on the signatures of about 10 percent of adult Sioux men. (Public Lands Institute, past work)'),
    (22, 'mount-rushmore-national-memorial', '_DSF2830',
     'Mount Rushmore National Memorial, South Dakota. The Supreme Court ruled in 1980 that the 1877 seizure of the Black Hills was unconstitutional; the Lakota have declined more than $1 billion in compensation and continue to assert their claim to the land. (Public Lands Institute, past work)'),
    (23, 'badlands-national-park', '_DSF2731',
     'Badlands National Park (North Unit), South Dakota. The 1868 Treaty of Fort Laramie guaranteed this country to the Oceti Sakowin "forever"; in 1980 the Supreme Court ruled the 1877 seizure of the Black Hills unconstitutional, and the Oceti Sakowin have refused the award and held out for the land. (Public Lands Institute, past work)'),
    (24, 'badlands-national-park', '_DSF2742',
     'Badlands National Park (North Unit), South Dakota. The Sioux Act of 1889 broke the Great Sioux Reservation into five smaller reservations; on Pine Ridge, south of this unit, the Army Air Force took land for a gunnery range in 1942 and relocated about 125 Oglala Lakota families. (Public Lands Institute, past work)'),
    (25, 'badlands-national-park', '_DSF2743',
     'Badlands National Park (North Unit), South Dakota. In 1968 Congress returned 202,357 acres of the former gunnery range to the Oglala Sioux Tribe; unexploded ordnance is still reported on that land, south of this unit. (Public Lands Institute, past work)'),
    (26, 'bears-ears-national-monument', '_DSF3473',
     'Bears Ears National Monument, Utah. Proclaimed in 2016 at the request of five tribal nations, the monument was cut in July 2026 to about 121,000 acres, and the five-tribe commission that co-managed it was disbanded. (Public Lands Institute, past work)'),
    (27, 'mesa-verde-national-park', '_DSF3525',
     'Mesa Verde National Park, Colorado. On land reserved to the Ute in 1868; in 1891 Gustaf Nordenskiöld excavated some twenty graves here and shipped the remains of Ancestral Pueblo people to Scandinavia, and Finland agreed to return them only in 2019 and 2020. (Public Lands Institute, past work)'),
    (28, 'bryce-canyon-national-park', '_DSF3252',
     'Bryce Canyon National Park, Utah. Unceded Southern Paiute homeland; after a 1954 act sponsored by Utah senator Arthur Watkins ended federal recognition, the Paiute Indian Tribe of Utah lost about 15,000 acres, and tribal accounts record that nearly half its members died before recognition returned in 1980. (Public Lands Institute, past work)'),
    (29, 'mammoth-cave-national-park', '_DSF0946',
     "Mammoth Cave National Park, Kentucky. Names written on the rock by visitors; the cave's first guides were enslaved men, among them Stephen Bishop and Mat and Nick Bransford, who mapped its passages from 1838. (Public Lands Institute, past work)"),
    (30, 'mammoth-cave-national-park', '_DSF0868',
     'Mammoth Cave National Park, Kentucky. When the park was assembled by eminent domain against 507 families, Black families were displaced with no provision for resettlement while white men kept the guiding work, and more than 70 cemeteries remain inside its boundaries. (Public Lands Institute, past work)'),
    (31, 'nantahala-national-forest', '_DSF3899',
     "Nantahala National Forest, North Carolina. An Alcoa power subsidiary finished Nantahala Lake in 1942 to supply aluminum for wartime aircraft; on the forest's edge, TVA's Fontana Dam, completed in 1944, displaced 1,311 families and moved 1,047 graves. (Public Lands Institute, past work)"),
    (32, 'great-smoky-mountains-national-park', '_DSF3940',
     'Great Smoky Mountains National Park, Tennessee. North Carolina and Tennessee assembled the park from 1926 to 1934 by purchase and condemnation of more than 1,100 tracts, many of them small farms; John W. Oliver, among the last residents of Cades Cove, left on Christmas Day 1937. (Public Lands Institute, past work)'),
    (33, 'caesar-creek', '_DSF0438',
     'Caesar Creek State Park, Ohio. The village of New Burlington lies under the reservoir; its last resident, 87-year-old Lawrence Mitchner, left on April 20, 1973. (Public Lands Institute, past work)'),
    (34, 'caesar-creek', '_DSF0419',
     'Caesar Creek State Park, Ohio. About 300 residents were displaced when the Army Corps of Engineers began acquiring the valley in the mid 1960s, and a Hopewell era village with 79 documented burials was flooded without preservation. (Public Lands Institute, past work)'),
    (35, 'falls-of-the-ohio-state-park', '_DSF4529',
     'Falls of the Ohio State Park, Indiana. Shippingport, a river town of some 600 people, was cut off into an island by the canal in 1830, and in 1958 the federal government condemned its last private property to widen the canal, evicting families who had lived there for over a century. (Public Lands Institute, past work)'),
    (36, 'arches-national-park', '_DSF3318',
     'Arches National Park, Utah. Ute homeland that no ratified treaty ceded; a mile from the park entrance, the Atlas uranium mill left about 16 million tons of tailings beside the Colorado River. (Public Lands Institute, past work)'),
    (37, 'black-hills-national-forest', '_DSF2896',
     'Black Hills National Forest, South Dakota. Congress seized the Black Hills from the Sioux in 1877, the year after the Homestake Mine began working at Lead; by its closing in 2002 the mine had put an estimated 75 million tons of tailings carrying 270,000 tons of arsenic into Whitewood Creek. (Public Lands Institute, past work)'),
    (38, 'black-hills-national-forest', '_DSF2890',
     'Black Hills National Forest, South Dakota. In the southern Hills, about 170 abandoned uranium mines from the weapons program of the 1950s to 1970s leach into the Cheyenne River watershed, with the heaviest impact on communities near the Pine Ridge Reservation. (Public Lands Institute, past work)'),
    (39, 'krejci-dump', '_DSF2105',
     'Krejci Dump, Cuyahoga Valley National Park, Ohio. Waste from Ford, General Motors, Chrysler and 3M was burned and buried here from 1948 to 1980, and the contamination came to light in 1986 when a person collecting scrap on the site fell ill. (Public Lands Institute, past work)'),
    (40, 'big-oaks-national-wildlife-refuge', '_DSF4273',
     'Big Oaks National Wildlife Refuge, Indiana. From 1984 to 1994 the Army fired about 100,000 kilograms of depleted-uranium tank rounds into an impact area here; roughly 70,000 kilograms remain, with no full cleanup planned, among an estimated 1.5 million unexploded rounds.')
]

SRGB = ImageCms.createProfile("sRGB")
SRGB_BYTES = ImageCms.ImageCmsProfile(SRGB).tobytes()


def find_source(slug, frame):
    for folder, exts in (("full", (".tif", ".tiff", ".TIF", ".TIFF")), ("jpg", (".jpg", ".JPG", ".jpeg"))):
        for ext in exts:
            p = os.path.join("img", folder, slug, frame + ext)
            if os.path.exists(p):
                return p, folder
    return None, None


def to_8bit_rgb(im):
    # 16-bit greyscale TIFFs: scale down to 8 bits before converting.
    if im.mode in ("I;16", "I;16B", "I;16L", "I"):
        im = im.point(lambda v: v / 256).convert("L")
    return im


def to_srgb(im):
    icc = im.info.get("icc_profile")
    im = to_8bit_rgb(im)
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            out_mode = "RGB"
            if im.mode == "L":
                im = im.convert("RGB")
            return ImageCms.profileToProfile(im, src, SRGB, outputMode=out_mode)
        except Exception as e:
            print(f"    colour profile not applied ({e}); converting directly")
    return im.convert("RGB")


def main():
    if not os.path.isdir("img"):
        sys.exit("Run this from the pli folder (the one containing img/).")
    os.makedirs(OUT, exist_ok=True)
    problems = []
    captions = []
    for n, slug, frame, caption in SELECTION:
        src, kind = find_source(slug, frame)
        name = f"{n:02d}_{slug}_{frame.lstrip('_')}.jpg"
        captions.append(f"{n:02d}  {name}\n{caption}\n")
        if not src:
            problems.append(f"{name}: no file found in img/full/{slug}/ or img/jpg/{slug}/")
            continue
        im = to_srgb(Image.open(src))
        w, h = im.size
        if max(w, h) > LONG_EDGE:
            s = LONG_EDGE / max(w, h)
            im = im.resize((round(w * s), round(h * s)), Image.LANCZOS)
        elif max(w, h) < LONG_EDGE:
            problems.append(f"{name}: source is only {max(w, h)} px ({src}); exported at that size, not upscaled")
        im.save(os.path.join(OUT, name), "JPEG", quality=QUALITY, dpi=DPI, icc_profile=SRGB_BYTES, optimize=True)
        print(f"{name:<70} {im.size[0]}x{im.size[1]}  from {kind}")
    with open(os.path.join(OUT, "captions.txt"), "w") as f:
        f.write("\n".join(captions))
    print(f"\nWrote {OUT}")
    if problems:
        print("\nCheck these:")
        for p in problems:
            print("  " + p)


if __name__ == "__main__":
    main()
