using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class MeshTrail : MonoBehaviour
{
    [SerializeField] public float activeTime = 2f;
    [SerializeField] public bool isActive;
    [SerializeField] private float meshDestroyDelay = 3f;
    
    private SkinnedMeshRenderer[] skinnedMeshRenderers;
    public Transform positionToSpawn;
    [SerializeField] private float meshRefreshRate = 0.1f;
    public Material mat;
    [SerializeField] ManaBar manaBar;
    // Start is called before the first frame update
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.M) && !isActive)
        {
            isActive = true;
            StartCoroutine(ActivateTrail(activeTime));
        }
    }

    public IEnumerator ActivateTrail(float timeActive)
    {
        while (timeActive > 0)
        {
            timeActive -= meshRefreshRate;

            if(skinnedMeshRenderers == null) 
            {
                skinnedMeshRenderers = GetComponentsInChildren<SkinnedMeshRenderer>();

            }

            for (int i = 0; skinnedMeshRenderers.Length > i; i++)
            {

                GameObject gObj = new GameObject();
                gObj.transform.SetPositionAndRotation(positionToSpawn.position, positionToSpawn.rotation);
                MeshRenderer mr= gObj.AddComponent<MeshRenderer>();
                MeshFilter mf= gObj.AddComponent<MeshFilter>();

                Mesh mesh = new Mesh();
                skinnedMeshRenderers[i].BakeMesh(mesh);

                mf.mesh = mesh;
                mr.material= mat;

                Destroy(gObj, meshDestroyDelay);
            }

            yield return new WaitForSeconds(meshRefreshRate);
        }

        isActive = false;
    }
}
