using System.Collections;
using System.Collections.Generic;
using UnityEngine;

public class followPlayer : MonoBehaviour
{
    [SerializeField] private float rotationSpeed;
    [SerializeField] private float speed;
    public float minDistance;
    [SerializeField] private float maxDistance;
    [SerializeField] Transform playerTransform;
    [SerializeField] private BeingDamaged BeingDamaged;
    [SerializeField] private bool Seen = false;
    public EnemySwordAnimation EnemySwordAnimation;
    [SerializeField] private EnemyHitbox enemyHitbox;

    // Start is called before the first frame update
    void Start()
    {
        
    }

    // Update is called once per frame
    void Update()
    {
        Vector3 directionToPlayer = playerTransform.position - transform.position;
        directionToPlayer.y = 0;
        if (!Seen && Vector3.Distance(transform.position, playerTransform.position) < maxDistance)
        {
            Seen = true;
        }
        if (Vector3.Distance(transform.position, playerTransform.position) > minDistance & !BeingDamaged.isBeingDamaged & Seen & !EnemySwordAnimation.isAttacking & !enemyHitbox.isParying)
        {
            transform.position = Vector3.MoveTowards(transform.position, playerTransform.position, speed* Time.deltaTime);
        }
        if (!BeingDamaged.isBeingDamaged & Seen & !EnemySwordAnimation.isAttacking)
        {
            if (transform.position != Vector3.zero)
            {
                Quaternion Target = Quaternion.LookRotation(directionToPlayer);
                transform.rotation = Quaternion.Slerp(transform.rotation, Target, rotationSpeed * Time.deltaTime);
            }
        }

    }
}
