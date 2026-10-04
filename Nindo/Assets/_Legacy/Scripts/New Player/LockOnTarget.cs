using System.Collections;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using TMPro;
using UnityEngine.UI;
public class LockOnTarget : MonoBehaviour
{
    //Mover camara en un punto medio
    [SerializeField] private Camera mainCamera;
    [SerializeField] private float normalFOV;
    [SerializeField] private float adjustedFOV;
    public float lerpSpeed;
    [SerializeField] Transform pivot;

    //Rotar al objetivo
    public float lockRange = 10f;
    public Transform targetTr;
    public GameObject target;
    [SerializeField] private LayerMask enemyLayer;
    public bool isLocked = false;


    //Rombo que se posiciona en el fijado
    [SerializeField] private Image indicatorImage;
    [SerializeField] private Vector3 imageOffset;

    // Start is called before the first frame update
    void Awake()
    {
        target = null;
        targetTr = null;
    }

    // Update is called once per frame
    void Update()
    {
        if (Input.GetKeyDown(KeyCode.Q) && LockOnClosestEnemies()!= null && !isLocked)
        {
            MoveCamera();
        } 
        else if (Input.GetKeyDown(KeyCode.Q) && isLocked)
        {
            ResetPosition();
            StopAdjustment();
        }
        if (targetTr != null && Vector3.Distance(transform.position, targetTr.transform.position) <= lockRange && isLocked)
        {
            LookAt();
            AdjustCamera();
        }
    }
    private void LateUpdate()
    {
        if (!isLocked || Vector3.Distance(transform.position, targetTr.transform.position) >= lockRange)
        {
            indicatorImage.enabled = false;
            StopAdjustment();
            ResetPosition();
        } 
        else
        {
            Vector3 screenPos = mainCamera.WorldToScreenPoint(targetTr.position + imageOffset);
            indicatorImage.enabled = true;
            indicatorImage.transform.position = screenPos;
        }

        
    }
    public GameObject LockOnClosestEnemies()
    {
        Collider[] enemies = Physics.OverlapSphere(transform.position, lockRange, enemyLayer);
        if (enemies.Length > 0)
        {
            var closest = enemies.OrderBy(e => Vector3.Distance(transform.position, e.transform.position)).FirstOrDefault();
            targetTr = closest.transform;
            target = closest.gameObject;
            return target;
        }
        return null;
    }
    void LookAt()
    {
        Vector3 direction = targetTr.position - pivot.position;
        direction.y = 0;
        Quaternion TargetRotation = Quaternion.LookRotation(direction);
        transform.rotation = Quaternion.Slerp(transform.rotation, TargetRotation, 30f * Time.deltaTime);
    }
    void AdjustCamera()
    {
        mainCamera.orthographicSize = Mathf.Lerp(mainCamera.orthographicSize, adjustedFOV, Time.deltaTime * lerpSpeed);
    }
    void StopAdjustment()
    {
        mainCamera.orthographicSize = Mathf.Lerp(mainCamera.orthographicSize, normalFOV, Time.deltaTime *lerpSpeed);
    }
    void MoveCamera()
    {
        isLocked = true;
    }
    void ResetPosition()
    {
        isLocked = false;
    }
}

