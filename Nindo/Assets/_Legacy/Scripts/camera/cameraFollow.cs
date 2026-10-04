using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class cameraFollow : MonoBehaviour
{
    [SerializeField] private Transform target;
    [SerializeField] private Vector3 offSet;
    [SerializeField] private LockOnTarget lockOnTarget;
    // Start is called before the first frame update
    void Start()
    {

    }

    // Update is called once per frame
    void LateUpdate()
    {
        Vector3 desiredPosition;
            if (lockOnTarget.isLocked && lockOnTarget.target != null)
            {
                Vector3 midpoint = (lockOnTarget.transform.position + lockOnTarget.targetTr.position) / 2f; 
                desiredPosition = midpoint + offSet;
            }
            else
            {
                desiredPosition = target.position + offSet;
            }
        transform.position = Vector3.Lerp(transform.position, desiredPosition, lockOnTarget.lerpSpeed *Time.deltaTime);
    }
}
