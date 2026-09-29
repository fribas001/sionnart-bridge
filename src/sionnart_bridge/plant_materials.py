"""P.833-10 leaf/wood dielectric inputs mapped to Sionna's slab material.

This is NOT an implementation of the P.833 canopy-scattering model. Sources,
units, convention and approximation limits are documented in PLANT_MATERIALS.md.
No Blender, Sionna or network dependency; evaluated again in every worker.
"""
import math

SOURCE_URL = 'https://www.itu.int/rec/R-REC-P.833-10-202109-I/en'
SIONNA_URL = 'https://nvlabs.github.io/sionna/rt/api/radio_materials.html'
MODEL_VERSION = 'p833-10-slab-v1'
EPSILON_0 = 8.8541878128e-12
MIN_FREQUENCY_HZ = 1e9
MAX_FREQUENCY_HZ = 30e9
MODEL_ITEMS = (
    ('LEAF_P833', 'Leaf — P.833 reference', 'Frequency-dependent reference leaf; thickness default 0.2 mm'),
    ('WOOD40_P833', 'Wood — 40% moisture, 20°C', 'Frequency-dependent wood from P.833-10 Table 10; effective slab approximation'),
)
# P.833-10 Table 10, not the different final frequency in older editions.
WOOD_TABLE = ((1.0, 7.2, .29), (2.4, 6.2, .30), (5.8, 6.0, .37), (30.0, 5.3, .43))
PRESETS = {
    'LEAF': {'name':'itu_plant_leaf_p833', 'label':'Leaf — 0.2 mm', 'model':'LEAF_P833',
             'thickness':.0002, 'color':(.09,.34,.045,1.), 'thickness_basis':'P.833-10 Table 9: leaf thickness 0.02 cm'},
    'TWIG': {'name':'itu_plant_twig_p833', 'label':'Moist wood — twig, 4 mm slab', 'model':'WOOD40_P833',
             'thickness':.004, 'color':(.24,.12,.035,1.), 'thickness_basis':'Effective slab using twice the Table 9 Branch (5) radius, 0.2 cm'},
    'BRANCH': {'name':'itu_plant_branch_p833', 'label':'Moist wood — branch, 56 mm slab', 'model':'WOOD40_P833',
               'thickness':.056, 'color':(.17,.075,.025,1.), 'thickness_basis':'Effective slab using twice the Table 9 Branch (3) radius, 2.8 cm'},
    'LARGE_BRANCH': {'name':'itu_plant_large_branch_p833', 'label':'Moist wood — large branch, 228 mm slab', 'model':'WOOD40_P833',
                     'thickness':.228, 'color':(.12,.052,.018,1.), 'thickness_basis':'Effective slab using twice the Table 9 Branch (1) radius, 11.4 cm'},
}
PRESET_ITEMS = tuple((k,p['label'],p['thickness_basis']) for k,p in PRESETS.items())


def evaluation_frequency(frequency_hz):
    f=float(frequency_hz)
    # Mitsuba may store frequency in float32 (30 GHz becomes 30000001024).
    # Accommodate endpoint representation only, never physical extrapolation.
    if not math.isfinite(f) or f < MIN_FREQUENCY_HZ*(1-1e-7) or f > MAX_FREQUENCY_HZ*(1+1e-7):
        raise ValueError('Plant reference materials support 1–30 GHz. Choose an in-range frequency or a documented Custom material; no extrapolation is applied.')
    return min(MAX_FREQUENCY_HZ,max(MIN_FREQUENCY_HZ,f))


def dielectric(model, frequency_hz):
    """Return (epsilon real, sigma S/m), with passive epsilon = er - j*loss.

    Wood loss tangent is a positive magnitude, independent of the phasor
    convention used to write P.833 equation (19). Never pass negative sigma.
    """
    f_hz=evaluation_frequency(frequency_hz)
    f=f_hz/1e9
    if model == 'LEAF_P833':
        eps=3.1686 + 28.938/(1+1j*f/18) - 1j*.5672/f
        er,loss=eps.real,-eps.imag
    elif model == 'WOOD40_P833':
        for left,right in zip(WOOD_TABLE,WOOD_TABLE[1:]):
            if left[0] <= f <= right[0]:
                weight=(f-left[0])/(right[0]-left[0])
                er=left[1]+weight*(right[1]-left[1])
                tangent=left[2]+weight*(right[2]-left[2])
                break
        loss=er*tangent
    else:
        raise ValueError('Unknown plant dielectric model: '+str(model))
    return float(er),float(2*math.pi*f_hz*EPSILON_0*loss)


def reference(model, frequency_hz, spec=None):
    """Self-describing receipt of the actual frequency and model assumptions."""
    spec=spec or {}
    er,sigma=dielectric(model,frequency_hz)
    preset_id=spec.get('plant_library_preset','')
    preset=PRESETS.get(preset_id,{})
    matches=preset.get('model')==model
    thickness=spec.get('thickness')
    baseline=spec.get('scattering_coefficient',0)==0 and spec.get('xpd_coefficient',0)==0
    return {
        'model_version':MODEL_VERSION, 'dielectric_model':model, 'source':'ITU-R P.833-10 (09/2021)',
        'source_url':SOURCE_URL, 'dielectric_reference':'Equation (18)' if model=='LEAF_P833' else 'Table 10; linear interpolation of epsilon real and loss tangent',
        'frequency_hz':float(frequency_hz), 'evaluation_frequency_hz':evaluation_frequency(frequency_hz),
        'frequency_range_hz':[MIN_FREQUENCY_HZ,MAX_FREQUENCY_HZ],
        'relative_permittivity':er, 'conductivity_s_m':sigma,
        'dielectric_loss_factor':sigma/(2*math.pi*evaluation_frequency(frequency_hz)*EPSILON_0),
        'wood_conditions':{'moisture_content_percent_as_reported':40,'temperature_c':20} if model=='WOOD40_P833' else None,
        'library_preset':preset_id if matches else None,
        'reference_thickness_m':preset.get('thickness') if matches else None,
        'thickness_basis':preset.get('thickness_basis') if matches else 'User-selected effective slab thickness',
        'thickness_overridden':bool(matches and thickness is not None and not math.isclose(float(thickness),preset['thickness'],rel_tol=1e-6,abs_tol=1e-10)),
        'surface_scattering_basis':'Smooth-surface baseline S=0, Kx=0; model assumption, not a measured plant constant' if baseline else 'User-selected effective-roughness parameters; not calibrated by the P.833 dielectric model',
        'solver_mapping':'Single-layer RadioMaterial slab, not the P.833 canopy-scattering model',
        'solver_reference_url':SIONNA_URL,
    }
