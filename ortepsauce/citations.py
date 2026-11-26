"""Literature references used in the SI caption (ACS style).

Checked against the publishers' DOI records (November 2026). %V_bur: the reference the SambVca
developers ask users to cite for buried-volume calculations (Poater 2008), the SambVca paper (2009),
SambVca 2.1 (2019, whose protocol and default settings are followed) and Bondi's radii. τ₄′: the
2015 paper and the 2018 paper on its usefulness. Every caption takes the text from this one table."""

# how to cite the program itself
ORTEPSAUCE_DOI = '10.5281/zenodo.24170231'
ORTEPSAUCE_URL = 'https://doi.org/' + ORTEPSAUCE_DOI
ORTEPSAUCE_CITATION = ('Saucedo Cañas, M. A.; Fortier, S. ORTEPSauce [Computer software]; Zenodo, 2026. '
                       'DOI: ' + ORTEPSAUCE_DOI)

REFS = {
    'tau4': ('Yang, L.; Powell, D. R.; Houser, R. P. Structural Variation in Copper(I) Complexes with '
             'Pyridylmethylamide Ligands: Structural Analysis with a New Four-Coordinate Geometry Index, τ4. '
             'Dalton Trans. 2007, 955–964. DOI: 10.1039/B617136B.'),
    'tau4p': ('Okuniewski, A.; Rosiak, D.; Chojnacki, J.; Becker, B. Coordination Polymers and Molecular '
              'Structures among Complexes of Mercury(II) Halides with Selected 1-Benzoylthioureas. '
              'Polyhedron 2015, 90, 47–57. DOI: 10.1016/j.poly.2015.01.035.'),
    'tau4p2': ('Rosiak, D.; Okuniewski, A.; Chojnacki, J. Novel Complexes Possessing Hg–(Cl, Br, I)···O=C '
               'Halogen Bonding and Unusual Hg2S2(Br/I)4 Kernel. The Usefulness of τ4′ Structural Parameter. '
               'Polyhedron 2018, 146, 35–41. DOI: 10.1016/j.poly.2018.02.016.'),
    'tau5': ('Addison, A. W.; Rao, T. N.; Reedijk, J.; van Rijn, J.; Verschoor, G. C. Synthesis, Structure, and '
             'Spectroscopic Properties of Copper(II) Compounds Containing Nitrogen–Sulphur Donor Ligands; the '
             'Crystal and Molecular Structure of Aqua[1,7-bis(N-methylbenzimidazol-2′-yl)-2,6-dithiaheptane]'
             'copper(II) Perchlorate. J. Chem. Soc., Dalton Trans. 1984, 1349–1356. DOI: 10.1039/DT9840001349.'),
    'vbur': ('Poater, A.; Ragone, F.; Giudice, S.; Costabile, C.; Dorta, R.; Nolan, S. P.; Cavallo, L. '
             'Thermodynamics of N-Heterocyclic Carbene Dimerization: The Balance of Sterics and Electronics. '
             'Organometallics 2008, 27, 2679–2681. DOI: 10.1021/om8001119.'),
    'sambvca': ('Poater, A.; Cosenza, B.; Correa, A.; Giudice, S.; Ragone, F.; Scarano, V.; Cavallo, L. SambVca: '
                'A Web Application for the Calculation of the Buried Volume of N-Heterocyclic Carbene Ligands. '
                'Eur. J. Inorg. Chem. 2009, 1759–1766. DOI: 10.1002/ejic.200801160.'),
    'sambvca21': ('Falivene, L.; Cao, Z.; Petta, A.; Serra, L.; Poater, A.; Oliva, R.; Scarano, V.; Cavallo, L. '
                  'Towards the Online Computer-Aided Design of Catalytic Pockets. Nat. Chem. 2019, 11, 872–879. '
                  'DOI: 10.1038/s41557-019-0319-5.'),
    'bondi': ('Bondi, A. van der Waals Volumes and Radii. J. Phys. Chem. 1964, 68, 441–451. '
              'DOI: 10.1021/j100785a001.'),
}

# which references each quantity needs, in citation order
NEEDS = {
    'τ₄': ['tau4'],
    'τ₄′': ['tau4p', 'tau4p2'],
    'τ₅': ['tau5'],
    '%Vbur': ['vbur', 'sambvca', 'sambvca21', 'bondi'],
}


class RefList:
    """Numbers references in the order they are first cited: ref('tau4') -> '[1]'."""

    def __init__(self, style='[n]'):
        self.keys = []
        self.style = style

    def num(self, key):
        if key not in self.keys:
            self.keys.append(key)
        return self.keys.index(key) + 1

    def cite(self, *keys):
        nums = [self.num(k) for k in keys if k in REFS]
        if not nums:
            return ''
        return '[' + ','.join(str(n) for n in nums) + ']'

    def text(self):
        if not self.keys:
            return ''
        return 'References\n' + '\n'.join(f'[{n}] {REFS[k]}' for n, k in enumerate(self.keys, 1))
