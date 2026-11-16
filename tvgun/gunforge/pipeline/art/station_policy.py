"""Scoped policy application; strict historical C03 results remain intact."""
def evaluate(policy,station_id,near_results,frame_results,slot_samples):
    if station_id!=policy['station_id']:raise ValueError('Station-scoped exception cannot apply elsewhere')
    if not slot_samples:raise ValueError('Slot evidence is required; layer diagnostic means alone cannot pass')
    limits=policy['slot'];ok=all(r['numeric_background_pass'] and r['normal_body_contrast']>=limits['normal_contrast_min'] and r['background_Yprime']>=limits['background_Yprime_min'] for r in slot_samples)
    ok=ok and all(r['status']=='pass' for r in near_results+frame_results)
    return {'status':'pass' if ok else 'fail','scope':'only supplied offline samples, not full engine/hardware coverage','policy_version':policy['version'],'layer_means':'diagnostic, historical original C03 retained','sample_count':len(slot_samples)}
