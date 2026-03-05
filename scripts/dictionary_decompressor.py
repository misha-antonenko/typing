# Thanks to commenters for providing the base of this much nicer implementation!
# Save and run with $ ipython dictionary_decompressor.py
# You may need to hunt down the dictionary files yourself and change the
# awful path string below.
# This works for me on MacOS 10.14 Mojave
import os
from struct import unpack
from zlib import decompress
import re

suffix = "/Contents/Resources/Body.data"
prefix = (
    "/System/Library/AssetsV2/com_apple_MobileAsset_DictionaryServices_dictionaryOSX/"
)

dictionaries = {
    "en_en": prefix + "1055914c8aac1752041bf58f559422844a5dd79e.asset/AssetData/Oxford "
    "Dictionary of English.dictionary" + suffix,
    "ru_en": prefix
    + "3841a4a7254118ff96f9b1bc854438ea7b1344ac.asset/AssetData/Russian "
    "- English.dictionary" + suffix,
    "fr_en": prefix + "6f45d9012c34086814df4e8f1415d2f94143a3d1.asset/AssetData/French "
    "- English.dictionary" + suffix,
    "en_en_thesaurus": prefix
    + "c1d6fe32a73dde515a2c9d08ee6671ec0c6b1a79.asset/AssetData/Oxford "
    "Thesaurus of English.dictionary" + suffix,
    "ru_ru": prefix + "e072c3a113b4696db6795c21e255d77f2e57ba69.asset/AssetData"
    "/Russian.dictionary" + suffix,
    "zhs_en": prefix + "22f9e1c8e9c04211e453909cfb6f5697153a9205.asset/AssetData/The "
    "Standard Dictionary of Contemporary Chinese.dictionary" + suffix,
    "jp_en": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/27c9b3d74dfa2f48d2c942aec21fcb0a1993c741.asset/AssetData/Sanseido Super "
    "Daijirin.dictionary/Contents/Resources/Body.data",
    "zht_zht": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/3085fe99a73e1548b8c9f8e515152e5c09792e10.asset/AssetData/Traditional "
    "Chinese.dictionary/Contents/Resources/Body.data",
    "es_en": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/3c8ec0bfe2d1ce3127349d62f25a73743c5959c3.asset/AssetData/Spanish - "
    "English.dictionary/Contents/Resources/Body.data",
    "it_en": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/4e08bb7862476c6654fdeb5b185ae88d1ec668e8.asset/AssetData/Italian - "
    "English.dictionary/Contents/Resources/Body.data",
    "es_es": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/6e58cbb7a33492e67a0ac64edde6dae15a2c7f41.asset/AssetData/Spanish"
    ".dictionary/Contents/Resources/Body.data",
    "fr_fr": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/74a60e797b349a86daddd0e928613f386c531f5b.asset/AssetData/French"
    ".dictionary/Contents/Resources/Body.data",
    "en_jp": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/7725cba5b321a8308a603a40ac808699175c4aae.asset/AssetData/Sanseido The "
    "WISDOM English-Japanese Japanese-English "
    "Dictionary.dictionary/Contents/Resources/Body.data",
    "zht_en": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/89fc1288feba671508e8c18a84c6e1f9cd740655.asset/AssetData/Traditional "
    "Chinese - English.dictionary/Contents/Resources/Body.data",
    "it_it": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/9f97e02eceaf43f17065d76b0940a99c783070e9.asset/AssetData/Italian"
    ".dictionary/Contents/Resources/Body.data",
    "ge_en": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/ef762d0dabf5341127bbfd2951961f0e1ba1a47c.asset/AssetData/German - "
    "English.dictionary/Contents/Resources/Body.data",
    "ar_en": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/f2c4d472ff26f172e0cf2447096031055fe52d08.asset/AssetData/Arabic - "
    "English.dictionary/Contents/Resources/Body.data",
    "ge_ge": "/System/Library/AssetsV2"
    "/com_apple_MobileAsset_DictionaryServices_dictionaryOSX"
    "/6a4ca7f723cefe0488359069b6a9e45e3a1b3765.asset/AssetData/Duden "
    "Dictionary Data Set I.dictionary/Contents/Resources/Body.data",
}


def form_and_save_dictionary(in_file_name, out_file_name):
    if os.path.exists(out_file_name):
        print(
            f"File {out_file_name} already exists, not sure if should overwrite.",
            end=" ",
        )
        return

    try:
        in_file = open(in_file_name, "rb")
    except FileNotFoundError:
        print("Not found.", end=" ")
        return

    in_file.seek(0x40)
    limit = 0x40 + unpack("i", in_file.read(4))[0]
    in_file.seek(0x60)

    def gen_entry():
        while in_file.tell() < limit:
            (sz,) = unpack("i", in_file.read(4))
            buf = decompress(in_file.read(sz)[8:])

            pos = 0
            while pos < len(buf):
                (chunk_size,) = unpack("i", buf[pos : pos + 4])
                pos += 4

                entry = buf[pos : pos + chunk_size]
                title = re.search(b'd:title="(.*?)"', entry).group(1)
                yield title.decode(), entry.decode()

                pos += chunk_size

    with open(out_file_name, "w") as out_file:
        for _, definition in gen_entry():
            out_file.write(definition)


def main():
    for name in dictionaries:
        print(f"Saving {name}...", end=" ")
        form_and_save_dictionary(dictionaries[name], "data/" + name + ".txt")
        print("Done.")


if __name__ == "__main__":
    main()
